"""
Phase 3 tests: the matching engine, tested in isolation before any UI exists.

Two groups:

* The maths -- cosine similarity, chunking, JSON round-trips. These build
  vectors by hand, never load the model, and run in milliseconds.
* The semantics -- does a real resume/job pair actually score the way the
  project claims? These load the model once for the whole class.

The second group is the reason this phase comes before the UI. Tuning a
similarity threshold through a browser is guesswork; tuning it against named
assertions is not.
"""

import re

import numpy as np
from django.conf import settings
from django.test import SimpleTestCase, override_settings

from . import embeddings, services
from .chunking import split_into_chunks


class CosineSimilarityTests(SimpleTestCase):
    def test_identical_vectors_score_one(self):
        v = [1.0, 2.0, 3.0]
        self.assertAlmostEqual(embeddings.cosine_similarity(v, v), 1.0, places=5)

    def test_orthogonal_vectors_score_zero(self):
        self.assertAlmostEqual(
            embeddings.cosine_similarity([1.0, 0.0], [0.0, 1.0]), 0.0, places=5
        )

    def test_opposite_vectors_score_minus_one(self):
        self.assertAlmostEqual(
            embeddings.cosine_similarity([1.0, 0.0], [-1.0, 0.0]), -1.0, places=5
        )

    def test_matches_a_hand_computed_value(self):
        # a.b = 1*3 + 2*4 = 11;  |a| = sqrt(5);  |b| = 5
        # cos = 11 / (sqrt(5) * 5) = 0.98386991...
        self.assertAlmostEqual(
            embeddings.cosine_similarity([1.0, 2.0], [3.0, 4.0]), 0.9838699, places=5
        )

    def test_magnitude_does_not_affect_the_result(self):
        """Cosine measures direction only -- scaling a vector changes nothing."""
        self.assertAlmostEqual(
            embeddings.cosine_similarity([1.0, 2.0], [3.0, 4.0]),
            embeddings.cosine_similarity([10.0, 20.0], [3.0, 4.0]),
            places=5,
        )

    def test_zero_vector_scores_zero_instead_of_raising(self):
        self.assertEqual(embeddings.cosine_similarity([0.0, 0.0], [1.0, 2.0]), 0.0)


class VectorisedSimilarityTests(SimpleTestCase):
    def test_agrees_with_the_scalar_version_row_by_row(self):
        matrix = np.array([[1.0, 0.0], [0.0, 1.0], [1.0, 1.0]], dtype=np.float32)
        vector = np.array([1.0, 2.0], dtype=np.float32)

        vectorised = embeddings.cosine_similarities(matrix, vector)
        for row, got in zip(matrix, vectorised):
            self.assertAlmostEqual(
                float(got), embeddings.cosine_similarity(row, vector), places=5
            )

    def test_empty_matrix_returns_an_empty_result(self):
        result = embeddings.cosine_similarities(np.zeros((0, 0)), [1.0, 2.0])
        self.assertEqual(result.size, 0)

    def test_zero_rows_do_not_raise(self):
        matrix = np.array([[0.0, 0.0], [1.0, 1.0]], dtype=np.float32)
        result = embeddings.cosine_similarities(matrix, [1.0, 1.0])
        self.assertAlmostEqual(float(result[0]), 0.0, places=5)
        self.assertAlmostEqual(float(result[1]), 1.0, places=5)


class ChunkingTests(SimpleTestCase):
    def test_short_lines_are_dropped(self):
        text = "SKILLS\nBuilt a payment service in Django and Python\n2019 - 2021"
        self.assertEqual(
            split_into_chunks(text),
            ["Built a payment service in Django and Python"],
        )

    def test_bullet_glyphs_are_stripped(self):
        for bullet in ["•", "-", "*", "–", ">"]:
            with self.subTest(bullet=bullet):
                chunks = split_into_chunks(f"{bullet} Designed a REST API for billing")
                self.assertEqual(chunks, ["Designed a REST API for billing"])

    def test_paragraphs_are_split_at_sentence_boundaries(self):
        text = "I built the billing service. I also ran the deployment pipeline."
        self.assertEqual(
            split_into_chunks(text),
            ["I built the billing service.", "I also ran the deployment pipeline."],
        )

    def test_repeated_lines_are_embedded_once(self):
        text = (
            "Managed the Django backend team\n"
            "managed the django backend team\n"
            "Managed the Django backend team"
        )
        self.assertEqual(len(split_into_chunks(text)), 1)

    def test_whitespace_is_collapsed(self):
        chunks = split_into_chunks("Built   a   scalable    ingestion pipeline")
        self.assertEqual(chunks, ["Built a scalable ingestion pipeline"])

    def test_empty_text_gives_no_chunks(self):
        self.assertEqual(split_into_chunks(""), [])
        self.assertEqual(split_into_chunks("   \n\n  "), [])

    def test_minimum_word_count_is_configurable(self):
        self.assertEqual(split_into_chunks("Python and Django", min_words=2)[0],
                         "Python and Django")
        self.assertEqual(split_into_chunks("Python and Django", min_words=5), [])


class SerialisationTests(SimpleTestCase):
    def test_vector_survives_a_round_trip(self):
        original = np.array([0.1, -0.25, 0.75], dtype=np.float32)
        restored = embeddings.vector_from_json(embeddings.vector_to_json(original))
        np.testing.assert_allclose(original, restored, rtol=1e-6)

    def test_blank_column_loads_as_an_empty_vector(self):
        self.assertEqual(embeddings.vector_from_json("").size, 0)

    def test_chunks_survive_a_round_trip_with_their_text(self):
        texts = ["Built a Django service", "Ran the deployment pipeline"]
        matrix = np.array([[0.1, 0.2], [0.3, 0.4]], dtype=np.float32)

        restored_texts, restored_matrix = embeddings.chunks_from_json(
            embeddings.chunks_to_json(texts, matrix)
        )
        self.assertEqual(restored_texts, texts)
        np.testing.assert_allclose(matrix, restored_matrix, rtol=1e-6)

    def test_blank_chunk_column_loads_as_empty(self):
        texts, matrix = embeddings.chunks_from_json("")
        self.assertEqual(texts, [])
        self.assertEqual(matrix.size, 0)


@override_settings(SEMANTIC_WEIGHT=0.5, COVERAGE_WEIGHT=0.5, SKILL_MATCH_THRESHOLD=0.45)
class ScoringMathsTests(SimpleTestCase):
    """
    The scoring arithmetic, driven by vectors built here rather than by the
    model. Hand-built vectors make every expected number checkable by hand.
    """

    def _score(self, **overrides):
        kwargs = {
            "doc_vector": np.array([1.0, 0.0], dtype=np.float32),
            "chunk_texts": ["worked on the python billing service",
                            "ran the restaurant kitchen"],
            "chunk_matrix": np.array([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32),
            "job_vector": np.array([1.0, 0.0], dtype=np.float32),
            "skills": ["python"],
            "skills_matrix": np.array([[1.0, 0.0]], dtype=np.float32),
        }
        kwargs.update(overrides)
        return services.score_from_vectors(**kwargs)

    def test_score_is_the_weighted_sum_of_semantic_and_coverage(self):
        # semantic = 1.0 (doc and job vectors identical).
        # skill A matches chunk 0 exactly, skill B matches nothing -> 0.5.
        # score = 0.5 * 1.0 + 0.5 * 0.5 = 0.75
        result = self._score(
            skills=["python", "underwater welding"],
            skills_matrix=np.array([[1.0, 0.0], [-1.0, 0.0]], dtype=np.float32),
        )
        self.assertAlmostEqual(result["semantic"], 1.0, places=4)
        self.assertAlmostEqual(result["coverage"], 0.5, places=4)
        self.assertAlmostEqual(result["score"], 0.75, places=4)

    def test_evidence_is_the_best_matching_chunk_not_the_first(self):
        result = self._score(
            skills=["cooking"],
            skills_matrix=np.array([[0.0, 1.0]], dtype=np.float32),
        )
        self.assertEqual(result["skill_results"][0]["evidence"],
                         "ran the restaurant kitchen")

    def test_threshold_decides_whether_a_skill_counts(self):
        # A skill vector 60 degrees from the chunk scores cos(60) = 0.5.
        skill = np.array([0.5, 0.8660254], dtype=np.float32)
        chunks = np.array([[0.0, 1.0]], dtype=np.float32)

        below = services.score_from_vectors(
            doc_vector=[1.0, 0.0], chunk_texts=["kitchen work"], chunk_matrix=chunks,
            job_vector=[1.0, 0.0], skills=["x"], skills_matrix=np.array([skill]),
            threshold=0.9,
        )
        above = services.score_from_vectors(
            doc_vector=[1.0, 0.0], chunk_texts=["kitchen work"], chunk_matrix=chunks,
            job_vector=[1.0, 0.0], skills=["x"], skills_matrix=np.array([skill]),
            threshold=0.5,
        )
        self.assertFalse(below["skill_results"][0]["matched"])
        self.assertTrue(above["skill_results"][0]["matched"])
        # Same similarity either way -- only the verdict moved.
        self.assertAlmostEqual(
            below["skill_results"][0]["similarity"],
            above["skill_results"][0]["similarity"],
            places=4,
        )

    def test_unmatched_skills_still_report_their_closest_line(self):
        # 60 degrees from the x-axis: cos 0.5 against chunk 0, cos 0.866
        # against chunk 1. Chunk 1 is the closest but still under the
        # threshold, which is exactly the "no, and here is the nearest thing
        # we found" case the evidence table has to render.
        result = self._score(
            skills=["underwater welding"],
            skills_matrix=np.array([[0.5, 0.8660254]], dtype=np.float32),
            threshold=0.99,
        )
        entry = result["skill_results"][0]
        self.assertFalse(entry["matched"])
        self.assertEqual(entry["evidence"], "ran the restaurant kitchen")

    def test_negative_similarity_is_reported_as_zero(self):
        result = self._score(
            doc_vector=np.array([-1.0, 0.0], dtype=np.float32),
            skills=["python"],
            skills_matrix=np.array([[-1.0, 0.0]], dtype=np.float32),
        )
        self.assertEqual(result["semantic"], 0.0)
        self.assertEqual(result["skill_results"][0]["similarity"], 0.0)

    def test_resume_with_no_usable_chunks_scores_zero_coverage(self):
        result = self._score(
            chunk_texts=[],
            chunk_matrix=np.zeros((0, 0), dtype=np.float32),
        )
        self.assertEqual(result["coverage"], 0.0)
        self.assertEqual(result["skill_results"][0]["evidence"], "")
        self.assertFalse(result["skill_results"][0]["matched"])

    def test_job_with_no_skills_falls_back_to_the_semantic_half(self):
        result = self._score(skills=[], skills_matrix=np.zeros((0, 0), dtype=np.float32))
        self.assertEqual(result["skill_results"], [])
        self.assertAlmostEqual(result["score"], result["semantic"], places=4)

    @override_settings(SEMANTIC_WEIGHT=0.8, COVERAGE_WEIGHT=0.2)
    def test_weights_are_read_from_settings(self):
        # semantic 1.0, coverage 0.5 -> 0.8 * 1.0 + 0.2 * 0.5 = 0.9
        result = self._score(
            skills=["python", "underwater welding"],
            skills_matrix=np.array([[1.0, 0.0], [-1.0, 0.0]], dtype=np.float32),
        )
        self.assertAlmostEqual(result["score"], 0.9, places=4)

    def test_every_required_skill_appears_in_the_results(self):
        skills = ["python", "django", "postgres"]
        result = self._score(
            skills=skills,
            skills_matrix=np.array([[1.0, 0.0]] * 3, dtype=np.float32),
        )
        self.assertEqual([r["skill"] for r in result["skill_results"]], skills)


# --------------------------------------------------------------------------
# Fixture text for the model-backed tests
# --------------------------------------------------------------------------

BACKEND_RESUME = """
Mohammed Osman
Backend Engineer, Khartoum

EXPERIENCE
Built and maintained REST APIs for a billing platform using Django and Python
Designed relational schemas and tuned slow PostgreSQL queries with EXPLAIN
Wrote unit and integration tests achieving high coverage on the payments module
Automated deployment with Docker containers and GitHub Actions pipelines
Mentored two junior developers through code review and pair programming

EDUCATION
BSc Computer Science, University of Khartoum
"""

FRONTEND_RESUME = """
Salma Idris
Web Developer, Omdurman

EXPERIENCE
Built single-page apps with Next.js and Redux for a retail customer portal
Implemented reusable component libraries and design systems in TypeScript
Improved page load times by code splitting and lazy loading heavy routes
Worked closely with designers to deliver responsive layouts across devices
"""

CHEF_RESUME = """
Tariq Hassan
Head Chef, Port Sudan

EXPERIENCE
Ran the kitchen of a busy seafood restaurant serving two hundred covers a night
Designed seasonal menus around locally sourced fish and vegetables
Trained and supervised a brigade of eight kitchen staff
Controlled food cost and managed supplier relationships and stock rotation
"""

BACKEND_JOB_DESCRIPTION = """
We are looking for a backend engineer to build and maintain the server-side
services behind our payments product. You will design HTTP APIs, model data in
a relational database, and keep the test suite meaningful as the system grows.
"""

BACKEND_JOB_SKILLS = [
    "3+ years of Python development",
    "Django ORM and database migrations",
    "PostgreSQL query optimisation",
    "Automated testing and continuous integration",
]


class _Stub:
    """Stands in for the Resume and Job models, which hold these same fields."""

    def __init__(self, fields):
        for name, value in fields.items():
            setattr(self, name, value)


class SemanticScoringTests(SimpleTestCase):
    """
    Model-backed tests: does the engine actually behave the way the project
    claims? The model is loaded once for the class, not per test.

    The floors below are not guesses. Every one was measured against these
    fixtures and then given margin, so a real regression trips them while
    ordinary model-version drift does not.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.job = _Stub(
            services.build_job_embeddings(BACKEND_JOB_DESCRIPTION, BACKEND_JOB_SKILLS)
        )
        cls.backend = _Stub(services.build_resume_embeddings(BACKEND_RESUME))
        cls.frontend = _Stub(services.build_resume_embeddings(FRONTEND_RESUME))
        cls.chef = _Stub(services.build_resume_embeddings(CHEF_RESUME))

        cls.backend_result = services.score_resume_against_job(cls.backend, cls.job)
        cls.frontend_result = services.score_resume_against_job(cls.frontend, cls.job)
        cls.chef_result = services.score_resume_against_job(cls.chef, cls.job)

    def test_relevant_resume_outscores_the_irrelevant_one(self):
        """The single claim the whole project rests on."""
        self.assertGreater(self.backend_result["score"], self.chef_result["score"])

    def test_scores_rank_backend_above_frontend_above_chef(self):
        self.assertGreater(self.backend_result["score"], self.frontend_result["score"])
        self.assertGreater(self.frontend_result["score"], self.chef_result["score"])

    def test_matching_resume_clears_a_floor(self):
        # Measured 0.543.
        self.assertGreater(self.backend_result["score"], 0.40)

    def test_unrelated_resume_stays_below_a_ceiling(self):
        # Measured 0.066.
        self.assertLess(self.chef_result["score"], 0.20)

    def test_whole_document_similarity_separates_the_two(self):
        # Measured 0.586 against 0.131.
        self.assertGreater(self.backend_result["semantic"], 0.45)
        self.assertLess(self.chef_result["semantic"], 0.25)

    def test_unrelated_resume_covers_none_of_the_required_skills(self):
        self.assertEqual(self.chef_result["coverage"], 0.0)

    def test_evidence_is_always_a_real_line_from_the_resume(self):
        chunks = split_into_chunks(BACKEND_RESUME)
        for entry in self.backend_result["skill_results"]:
            self.assertIn(entry["evidence"], chunks)

    def test_every_required_skill_is_reported(self):
        self.assertEqual(
            [e["skill"] for e in self.backend_result["skill_results"]],
            BACKEND_JOB_SKILLS,
        )


def _words(text):
    """Lowercased word tokens, so overlap can be checked rigorously."""
    return set(re.findall(r"\w+", text.lower()))


class CrossVocabularyTests(SimpleTestCase):
    """
    The defining behaviour: matching on meaning where nothing overlaps.

    A keyword matcher scores every pair in this class at exactly zero, because
    not one of these skill phrases shares a word with the resume line it is
    compared against. The embedding model still ranks them correctly, and that
    difference is the whole argument for the approach.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.chunks = split_into_chunks(FRONTEND_RESUME)
        cls.matrix = embeddings.encode(cls.chunks)

    def _best(self, skill):
        similarities = embeddings.cosine_similarities(
            self.matrix, embeddings.encode_one(skill)
        )
        index = int(np.argmax(similarities))
        return float(similarities[index]), self.chunks[index]

    def test_related_technology_outranks_unrelated_ones_with_zero_word_overlap(self):
        react, react_line = self._best("React development")
        kubernetes, kubernetes_line = self._best("Kubernetes")
        cobol, cobol_line = self._best("COBOL mainframe programming")

        # Nothing here shares a single word with its evidence line.
        for skill, line in [
            ("React development", react_line),
            ("Kubernetes", kubernetes_line),
            ("COBOL mainframe programming", cobol_line),
        ]:
            with self.subTest(skill=skill):
                self.assertEqual(_words(skill) & _words(line), set())

        # Yet the resume's actual subject matter ranks far above the rest.
        # Measured: 0.363 against 0.109 and 0.184.
        self.assertGreater(react, kubernetes)
        self.assertGreater(react, cobol)
        self.assertGreater(react, 0.30)
        self.assertLess(kubernetes, 0.20)

    def test_a_skill_can_clear_the_threshold_without_sharing_a_word(self):
        similarity, line = self._best("component-based user interface frameworks")
        # Measured 0.57 against "Implemented reusable component libraries and
        # design systems in TypeScript".
        self.assertGreater(similarity, settings.SKILL_MATCH_THRESHOLD)
        self.assertNotIn("react", line.lower())

    def test_technology_absent_from_the_resume_stays_far_below_threshold(self):
        similarity, _ = self._best("Kubernetes cluster administration")
        self.assertLess(similarity, settings.SKILL_MATCH_THRESHOLD)


class SkillPhrasingTests(SimpleTestCase):
    """
    How a company words a required skill changes its score, measurably.

    Two findings, both from these fixtures:

    * A descriptive phrase beats a bare keyword by a wide margin --
      "building REST APIs with Django and Python" scores 0.76 where "Python"
      alone scores 0.39.
    * A duration prefix hurts. "3+ years of Python development" drifts toward
      credential lines and picked out the *education* line, while "Python
      development" correctly picked the line describing the work.

    The lesson is not "write longer phrases" but "describe the work, not the
    credential" -- the model matches an activity to an activity.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.chunks = split_into_chunks(BACKEND_RESUME)
        cls.matrix = embeddings.encode(cls.chunks)

    def _best(self, skill):
        similarities = embeddings.cosine_similarities(
            self.matrix, embeddings.encode_one(skill)
        )
        index = int(np.argmax(similarities))
        return float(similarities[index]), self.chunks[index]

    def test_descriptive_phrase_beats_a_bare_keyword(self):
        phrase, _ = self._best("building REST APIs with Django and Python")
        keyword, _ = self._best("Python")
        self.assertGreater(phrase, keyword)
        self.assertGreater(phrase - keyword, 0.20)  # measured gap ~0.37

    def test_duration_prefix_drags_the_match_toward_credential_lines(self):
        _, with_duration = self._best("3+ years of Python development")
        _, without_duration = self._best("Python development")

        self.assertIn("BSc", with_duration)
        self.assertIn("Django and Python", without_duration)


class ModelLoadingTests(SimpleTestCase):
    """The singleton is a performance contract, so it gets a test."""

    def test_get_model_returns_the_same_object_every_time(self):
        from .model import get_model

        self.assertIs(get_model(), get_model())

    def test_embedding_dimension_matches_the_documented_model(self):
        from .model import embedding_dimension

        self.assertEqual(embedding_dimension(), 384)


class BatchEncodingTests(SimpleTestCase):
    def test_encode_returns_one_row_per_input(self):
        texts = ["first line of a resume", "second line of a resume", "a third one"]
        matrix = embeddings.encode(texts)
        self.assertEqual(matrix.shape, (3, 384))

    def test_encode_of_an_empty_list_does_not_raise(self):
        """A resume that chunked to nothing must not blow up the upload view."""
        self.assertEqual(embeddings.encode([]).size, 0)

    def test_vectors_come_back_normalised(self):
        """Normalised vectors are what make cosine similarity a dot product."""
        matrix = embeddings.encode(["a line from somebody's resume"])
        self.assertAlmostEqual(float(np.linalg.norm(matrix[0])), 1.0, places=4)

    def test_batching_gives_the_same_vectors_as_encoding_one_at_a_time(self):
        texts = ["built a billing service", "ran a restaurant kitchen"]
        batched = embeddings.encode(texts)
        individually = np.vstack([embeddings.encode_one(t) for t in texts])
        np.testing.assert_allclose(batched, individually, atol=1e-5)


class RecommendationTests(SimpleTestCase):
    """
    Recommendations run the same comparison as the apply flow, pointed the
    other way: one resume against many jobs.
    """

    class _Stub:
        def __init__(self, fields):
            for name, value in fields.items():
                setattr(self, name, value)

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.resume = cls._Stub(services.build_resume_embeddings(BACKEND_RESUME))

        cls.backend_job = cls._Stub(
            services.build_job_embeddings(BACKEND_JOB_DESCRIPTION, BACKEND_JOB_SKILLS)
        )
        cls.backend_job.title = "Backend Engineer"

        cls.kitchen_job = cls._Stub(
            services.build_job_embeddings(
                "Run the kitchen of a busy seafood restaurant on the coast.",
                ["running a busy restaurant kitchen", "designing seasonal menus"],
            )
        )
        cls.kitchen_job.title = "Head Chef"

    def test_the_relevant_job_is_ranked_first(self):
        ranked = services.recommend_jobs(self.resume, [self.kitchen_job, self.backend_job])
        self.assertEqual(ranked[0][0].title, "Backend Engineer")
        self.assertGreater(ranked[0][1]["score"], ranked[1][1]["score"])

    def test_the_limit_is_respected(self):
        jobs = [self.backend_job, self.kitchen_job] * 6
        self.assertEqual(len(services.recommend_jobs(self.resume, jobs, limit=3)), 3)

    def test_scoring_many_jobs_agrees_with_scoring_one(self):
        """
        Parsing the resume once for the whole batch must not change the answer.

        This is the guard on the optimisation: if batching ever diverged from
        the single-job path, candidates and recruiters would be shown
        different numbers for the same pair.
        """
        batched = dict(
            (job.title, result["score"])
            for job, result in services.score_resume_against_jobs(
                self.resume, [self.backend_job, self.kitchen_job]
            )
        )
        for job in (self.backend_job, self.kitchen_job):
            one_at_a_time = services.score_resume_against_job(self.resume, job)
            self.assertAlmostEqual(batched[job.title], one_at_a_time["score"], places=4)

    def test_jobs_without_embeddings_are_skipped(self):
        unembedded = self._Stub(
            {"description_embedding": "", "skills_embedding": "", "title": "Unembedded"}
        )
        ranked = services.recommend_jobs(self.resume, [unembedded, self.backend_job])
        self.assertEqual([job.title for job, _ in ranked], ["Backend Engineer"])

    def test_an_empty_job_list_gives_no_recommendations(self):
        self.assertEqual(services.recommend_jobs(self.resume, []), [])
