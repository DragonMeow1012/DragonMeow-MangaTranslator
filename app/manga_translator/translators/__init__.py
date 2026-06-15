import itertools
from typing import Optional, List

from .common import *
from .gemini_2stage import Gemini2StageTranslator
from ..config import Translator, TranslatorConfig, TranslatorChain
from ..utils import Context

# 只保留 gemini_2stage（DCbot 唯一使用的 backend）
TRANSLATORS = {
    Translator.gemini_2stage: Gemini2StageTranslator,
}
translator_cache = {}

# 並發起始 key 分散用：帶 per-request config 的 dispatch 每次從不同 key 起跳，
# 避免 K 頁同時打同一把 key 撞 429。單執行緒 event loop 下 next() 為原子操作。
_dispatch_seq = itertools.count()


def get_translator(key: Translator, *args, **kwargs) -> CommonTranslator:
    if key not in TRANSLATORS:
        raise ValueError(
            f'Could not find translator for: "{key}". '
            f'Choose from: {",".join(t.value for t in TRANSLATORS)}'
        )
    if not translator_cache.get(key):
        translator = TRANSLATORS[key]
        translator_cache[key] = translator(*args, **kwargs)
    return translator_cache[key]


async def prepare(chain: TranslatorChain):
    for key, tgt_lang in chain.chain:
        translator = get_translator(key)
        translator.supports_languages('auto', tgt_lang, fatal=True)


async def dispatch(
    chain: TranslatorChain, queries: List[str],
    translator_config: Optional[TranslatorConfig] = None,
    use_mtpe: bool = False, args: Optional[Context] = None, device: str = 'cpu',
) -> List[str]:
    if not queries:
        return queries
    if args is not None:
        args['translations'] = {}
    for key, tgt_lang in chain.chain:
        if translator_config:
            # 並發安全（修「連續翻譯隨機散點/漏翻」）：帶 per-request config 時用「獨立實例」，
            # 不用共用單例。否則 K 頁並發下，某頁在無鎖的 LLM await 期間，另一頁的 parse_args
            # 會覆蓋共用實例的 _api_keys/_provider/_send_image/refine_model 並把 _call_idx 歸零
            # → 該頁醒來讀到別頁的設定 → 打錯 key/模型、回空 → 整格漏翻 → 渲染成「…」散點。
            # bot 端的 gemini_2stage 沒有 parse_args override（resolve 到 base no-op）故不踩此雷；
            # web 端有 override → 必須每頁隔離，行為才對齊 bot。API 翻譯器無模型載入，新建很便宜。
            translator = TRANSLATORS[key]()
            translator.parse_args(translator_config)
            _keys = getattr(translator, '_api_keys', None)
            if _keys:
                translator._call_idx = next(_dispatch_seq) % len(_keys)
        else:
            translator = get_translator(key)
        # gemini_2stage 簽名跟一般 translator 不同（吃 ctx 而非 use_mtpe）
        queries = await translator.translate('auto', tgt_lang, queries, args)
        if args is not None:
            args['translations'][tgt_lang] = queries
    return queries


async def dispatch_batch(
    chain: TranslatorChain, batch_queries: List[List[str]],
    translator_config: Optional[TranslatorConfig] = None,
    use_mtpe: bool = False, args: Optional[Context] = None, device: str = 'cpu',
) -> List[List[str]]:
    if not batch_queries or not any(batch_queries):
        return batch_queries
    flat_queries = []
    query_mapping = []
    for batch_idx, queries in enumerate(batch_queries):
        for query in queries:
            flat_queries.append(query)
            query_mapping.append(batch_idx)
    flat_results = await dispatch(chain, flat_queries, translator_config, use_mtpe, args, device)
    batch_results = [[] for _ in batch_queries]
    for result, batch_idx in zip(flat_results, query_mapping):
        batch_results[batch_idx].append(result)
    return batch_results


async def unload(key: Translator):
    translator_cache.pop(key, None)
