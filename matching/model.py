"""
The sentence-transformers model, loaded once per process.

Loading the model reads roughly 90 MB from disk and takes several seconds. A
web request that did that would be unusable, so the model is held in a
module-level singleton: the first call pays the cost, every call afterwards
gets the already-loaded object back.
"""

import logging

from django.conf import settings

logger = logging.getLogger(__name__)

# Module-level, so it survives for the lifetime of the process. This is the
# whole caching strategy -- there is no need for anything more.
_model = None


def get_model():
    """
    Return the shared SentenceTransformer, loading it on first use.

    The first call downloads the model (~90 MB) if it is not already cached on
    disk, which takes about ten seconds. Every later call is effectively free.
    """
    global _model
    if _model is None:
        # Imported here rather than at module scope on purpose. Importing
        # sentence_transformers pulls in torch, which adds seconds to startup.
        # Keeping it inside the function means `manage.py migrate` and the
        # views that never embed anything do not pay that cost.
        from sentence_transformers import SentenceTransformer

        logger.info("Loading embedding model %s", settings.EMBEDDING_MODEL_NAME)
        _model = SentenceTransformer(settings.EMBEDDING_MODEL_NAME)
        logger.info("Embedding model loaded")

    return _model


def embedding_dimension():
    """Vector width of the active model. 384 for all-MiniLM-L6-v2."""
    return get_model().get_sentence_embedding_dimension()
