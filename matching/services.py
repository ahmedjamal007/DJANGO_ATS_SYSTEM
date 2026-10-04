"""
The scoring engine. This is the core of the project.

Every comparison here is between vectors. No string is ever compared with
another string: a job requiring "React" matches a resume line reading "built
single-page apps with Next.js and Redux" because the model places those two
phrases near each other in vector space, and that is precisely the behaviour
the project exists to demonstrate.

A score has three parts:

1. semantic  -- cosine similarity between the whole resume and the whole job
                description. Answers "is this person broadly a fit".
2. coverage  -- the fraction of the job's required skills that the resume
                evidences, judged per skill against every resume chunk.
3. score     -- SEMANTIC_WEIGHT * semantic + COVERAGE_WEIGHT * coverage.

Weights and the match threshold live in settings.py so they can be tuned from
evidence rather than edited into the code.
"""

import numpy as np
from django.conf import settings

from . import embeddings
from .chunking import split_into_chunks


def _clamp_unit(value):
    """
    Squash a similarity into 0-1.

    Cosine similarity is defined on -1 to 1. A negative value means "pointing
    away", which for our purposes is no better than unrelated, so it is
    reported as 0 rather than dragging a weighted average below zero.
    """
    return float(max(0.0, min(1.0, value)))


# --------------------------------------------------------------------------
# Building embeddings (used by Phase 4 for resumes and Phase 5 for jobs)
# --------------------------------------------------------------------------


def build_resume_embeddings(text):
    """
    Embed a resume twice: once whole, once per chunk.

    Returns the two JSON strings the Resume model stores, plus the chunk count
    for display. Both encodes are batched.
    """
    chunk_texts = split_into_chunks(text)

    doc_vector = embeddings.encode_one(text)
    chunk_matrix = embeddings.encode(chunk_texts)

    return {
        "doc_embedding": embeddings.vector_to_json(doc_vector),
        "chunk_embeddings": embeddings.chunks_to_json(chunk_texts, chunk_matrix),
        "chunk_count": len(chunk_texts),
    }


def build_job_embeddings(description, skill_lines):
    """
    Embed a job description and each of its required-skill phrases.

    Done once when the job is saved, so applying to it later does not re-run
    the model. The skill phrases are encoded as one batch.
    """
    skill_lines = [line for line in skill_lines if line.strip()]

    description_vector = embeddings.encode_one(description)
    skills_matrix = embeddings.encode(skill_lines)

    return {
        "description_embedding": embeddings.vector_to_json(description_vector),
        "skills_embedding": embeddings.chunks_to_json(skill_lines, skills_matrix),
    }


# --------------------------------------------------------------------------
# Scoring
# --------------------------------------------------------------------------


def score_from_vectors(
    *,
    doc_vector,
    chunk_texts,
    chunk_matrix,
    job_vector,
    skills,
    skills_matrix,
    threshold=None,
):
    """
    The scoring maths, taking vectors rather than model instances.

    Kept separate from `score_resume_against_job` so it can be unit-tested
    against fixture text without a database, which is why Phase 3 exists
    before any of the UI.
    """
    if threshold is None:
        threshold = settings.SKILL_MATCH_THRESHOLD

    semantic = _clamp_unit(embeddings.cosine_similarity(doc_vector, job_vector))

    if not skills:
        # Defensive only: the job form requires at least one skill line. With
        # nothing to cover there is no coverage to measure, so the score falls
        # back to the half we can measure instead of reporting a misleading 0.
        return {
            "score": round(semantic, 4),
            "semantic": round(semantic, 4),
            "coverage": 0.0,
            "skill_results": [],
        }

    skill_results = []
    matched_count = 0

    for index, skill in enumerate(skills):
        # One vectorised pass per skill across every chunk. The maximum is the
        # score: we want the single best piece of evidence in the resume, not
        # an average that a long unrelated CV would water down.
        similarities = embeddings.cosine_similarities(chunk_matrix, skills_matrix[index])

        if similarities.size:
            best_index = int(np.argmax(similarities))
            best_similarity = _clamp_unit(similarities[best_index])
            evidence = chunk_texts[best_index]
        else:
            # A resume that produced no usable chunks -- a scanned image, or
            # text too short to survive chunking.
            best_similarity = 0.0
            evidence = ""

        matched = best_similarity >= threshold
        if matched:
            matched_count += 1

        skill_results.append(
            {
                "skill": skill,
                "similarity": round(best_similarity, 4),
                "matched": matched,
                # Kept even when unmatched: "closest thing we found" is more
                # useful to a recruiter than a bare no.
                "evidence": evidence,
            }
        )

    coverage = matched_count / len(skills)
    score = settings.SEMANTIC_WEIGHT * semantic + settings.COVERAGE_WEIGHT * coverage

    return {
        "score": round(score, 4),
        "semantic": round(semantic, 4),
        "coverage": round(coverage, 4),
        "skill_results": skill_results,
    }


def score_resume_against_job(resume, job):
    """
    Score a stored Resume against a stored Job.

    Reads the vectors both objects already hold -- nothing is re-embedded here,
    which is why applying to a job is fast even though creating one is not.

    `resume` is duck-typed: anything exposing `doc_embedding` and
    `chunk_embeddings` works. The Resume model itself arrives in Phase 4.
    """
    chunk_texts, chunk_matrix = embeddings.chunks_from_json(resume.chunk_embeddings)
    skills, skills_matrix = embeddings.chunks_from_json(job.skills_embedding)

    return score_from_vectors(
        doc_vector=embeddings.vector_from_json(resume.doc_embedding),
        chunk_texts=chunk_texts,
        chunk_matrix=chunk_matrix,
        job_vector=embeddings.vector_from_json(job.description_embedding),
        skills=skills,
        skills_matrix=skills_matrix,
    )


def score_resume_against_jobs(resume, jobs):
    """
    Score one resume against many jobs, cheaply.

    The resume's vectors are parsed out of JSON exactly once and reused for
    every job, rather than being re-parsed inside the loop. That is the whole
    optimisation: the candidate side is identical for every comparison, so
    decoding it fifteen times would be fifteen times the work for the same
    answer.

    Returns a list of (job, result) ordered as `jobs` was. Jobs with no
    embeddings are skipped -- they would score zero against everyone and
    reading that as "bad match" would be wrong.
    """
    chunk_texts, chunk_matrix = embeddings.chunks_from_json(resume.chunk_embeddings)
    doc_vector = embeddings.vector_from_json(resume.doc_embedding)

    scored = []
    for job in jobs:
        if not job.description_embedding or not job.skills_embedding:
            continue

        skills, skills_matrix = embeddings.chunks_from_json(job.skills_embedding)
        result = score_from_vectors(
            doc_vector=doc_vector,
            chunk_texts=chunk_texts,
            chunk_matrix=chunk_matrix,
            job_vector=embeddings.vector_from_json(job.description_embedding),
            skills=skills,
            skills_matrix=skills_matrix,
        )
        scored.append((job, result))

    return scored


def recommend_jobs(resume, jobs, limit=10):
    """
    The best-matching open jobs for a candidate, highest score first.

    This is the same comparison the apply flow runs, pointed the other way:
    one resume against many jobs instead of many resumes against one job.
    Using the identical function is the point -- a candidate is never shown a
    ranking built on different arithmetic from the one recruiters see.
    """
    scored = score_resume_against_jobs(resume, jobs)
    scored.sort(key=lambda pair: pair[1]["score"], reverse=True)
    return scored[:limit]
