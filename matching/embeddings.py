"""
Encoding text to vectors, comparing vectors, and storing them.

Everything here is NumPy. SQLite has no vector type, so embeddings are kept as
JSON in text columns and loaded into arrays when needed. With resume counts in
the hundreds, a brute-force cosine similarity over an in-memory array is fast
enough that a vector database would be solving a problem this project does not
have.
"""

import json

import numpy as np

from .model import get_model


def encode(texts):
    """
    Batch-encode a list of strings into an (n, dim) float32 array.

    Always batch. `model.encode(list_of_texts)` runs one forward pass over the
    whole list, while a loop of single calls pays the per-call overhead every
    time and is several times slower on a resume with fifty lines.

    Vectors come back L2-normalised, which makes cosine similarity equal to a
    plain dot product. `cosine_similarity` below does not rely on that -- it
    divides by the norms anyway -- so the maths stays correct for any vector.
    """
    texts = list(texts)
    if not texts:
        return np.zeros((0, 0), dtype=np.float32)

    vectors = get_model().encode(
        texts,
        normalize_embeddings=True,
        convert_to_numpy=True,
        show_progress_bar=False,
    )
    return np.asarray(vectors, dtype=np.float32)


def encode_one(text):
    """Encode a single string. A thin wrapper over the batch call."""
    return encode([text])[0]


# --------------------------------------------------------------------------
# Similarity
# --------------------------------------------------------------------------


def cosine_similarity(a, b):
    """
    Cosine similarity between two vectors: the dot product over the product of
    the magnitudes. Result runs from -1 (opposite) through 0 (unrelated) to 1
    (identical direction).

    Written out in full rather than assuming normalised input, so the function
    is correct on its own and can be checked against hand-computed values.
    """
    a = np.asarray(a, dtype=np.float32)
    b = np.asarray(b, dtype=np.float32)

    denominator = float(np.linalg.norm(a) * np.linalg.norm(b))
    if denominator == 0.0:
        # A zero vector has no direction, so no angle is defined. Zero is the
        # honest answer, and it keeps an empty resume from raising.
        return 0.0

    return float(np.dot(a, b) / denominator)


def cosine_similarities(matrix, vector):
    """
    Cosine similarity of `vector` against every row of `matrix`, at once.

    This is the vectorised version and it is the one the scorer uses. Looping
    in Python over a queryset, parsing JSON each time, is the slow path this
    project explicitly avoids: load the vectors into one array, then let NumPy
    do the arithmetic in a single operation.
    """
    matrix = np.asarray(matrix, dtype=np.float32)
    vector = np.asarray(vector, dtype=np.float32)

    if matrix.size == 0:
        return np.zeros(0, dtype=np.float32)

    denominators = np.linalg.norm(matrix, axis=1) * float(np.linalg.norm(vector))
    # Guard rows that are all zeros; their similarity stays 0 after the divide.
    denominators[denominators == 0.0] = 1.0

    return (matrix @ vector) / denominators


# --------------------------------------------------------------------------
# Storage: vectors live in TextField columns as JSON
# --------------------------------------------------------------------------


def vector_to_json(vector):
    """Serialise one vector for a TextField."""
    return json.dumps([float(x) for x in np.asarray(vector).ravel()])


def vector_from_json(text):
    """Load one vector. Returns an empty array when the column is blank."""
    if not text:
        return np.zeros(0, dtype=np.float32)
    return np.asarray(json.loads(text), dtype=np.float32)


def chunks_to_json(texts, vectors):
    """
    Serialise chunk texts alongside their vectors.

    The text is stored with the vector rather than re-derived later, because
    the evidence line shown to a recruiter has to be the exact passage that
    produced the score.
    """
    vectors = np.asarray(vectors, dtype=np.float32)
    return json.dumps(
        [
            {"text": text, "vector": [float(x) for x in vector]}
            for text, vector in zip(texts, vectors)
        ]
    )


def chunks_from_json(text):
    """
    Load chunks as (list_of_texts, matrix).

    Returning the vectors as one array is the point: the caller gets something
    it can hand straight to `cosine_similarities` without a Python loop.
    """
    if not text:
        return [], np.zeros((0, 0), dtype=np.float32)

    records = json.loads(text)
    if not records:
        return [], np.zeros((0, 0), dtype=np.float32)

    texts = [record["text"] for record in records]
    matrix = np.asarray([record["vector"] for record in records], dtype=np.float32)
    return texts, matrix
