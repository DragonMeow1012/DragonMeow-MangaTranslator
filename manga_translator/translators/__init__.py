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
        translator = get_translator(key)
        if translator_config:
            translator.parse_args(translator_config)
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
