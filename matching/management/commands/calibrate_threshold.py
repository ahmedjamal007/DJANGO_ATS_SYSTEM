"""
Choose SKILL_MATCH_THRESHOLD from evidence instead of guessing it.

    python manage.py calibrate_threshold

The threshold decides when a required skill counts as met. It is a judgement
call, not a fact -- but it does not have to be an uninformed one.

Every sample resume and every sample job in sample_data/ carries a category
(backend, frontend, data, devops, hospitality, finance). That gives ground
truth: a skill compared against a resume from the *same* field is a pair that
should match, and one from a *different* field is a pair that should not. This
command scores every such pair, prints the two distributions, and reports the
threshold that separates them best.

Nothing is written. The command reports; a human edits settings.py.
"""

from django.conf import settings
from django.core.management.base import BaseCommand

from matching import embeddings
from matching.chunking import split_into_chunks
from sample_data import profiles


class Command(BaseCommand):
    help = "Report the similarity distributions that SKILL_MATCH_THRESHOLD has to separate."

    def add_arguments(self, parser):
        parser.add_argument(
            "--step",
            type=float,
            default=0.01,
            help="Granularity of the threshold sweep (default 0.01).",
        )

    def handle(self, *args, **options):
        self.stdout.write("Encoding sample resumes and job skills...")

        # Encode once per resume, not once per pair.
        resume_chunks = {}
        for resume in profiles.RESUMES:
            chunks = split_into_chunks(resume.text)
            resume_chunks[resume.filename] = (
                resume.category,
                chunks,
                embeddings.encode(chunks),
            )

        # Every skill line from every sample job, with the field it belongs to.
        skill_lines, skill_categories = [], []
        for job in profiles.JOBS:
            for skill in job.skills:
                skill_lines.append(skill)
                skill_categories.append(job.category)
        skill_matrix = embeddings.encode(skill_lines)

        same_field, different_field = [], []
        worst_true_positive = None
        best_false_positive = None

        for index, skill in enumerate(skill_lines):
            skill_vector = skill_matrix[index]
            skill_category = skill_categories[index]

            for filename, (category, chunks, matrix) in resume_chunks.items():
                if matrix.size == 0:
                    continue

                similarities = embeddings.cosine_similarities(matrix, skill_vector)
                best = float(similarities.max())
                evidence = chunks[int(similarities.argmax())]

                if category == skill_category:
                    same_field.append(best)
                    if worst_true_positive is None or best < worst_true_positive[0]:
                        worst_true_positive = (best, skill, evidence)
                else:
                    different_field.append(best)
                    if best_false_positive is None or best > best_false_positive[0]:
                        best_false_positive = (best, skill, evidence)

        self._report(same_field, different_field, worst_true_positive,
                     best_false_positive, options["step"])

    # ----------------------------------------------------------------- #

    def _report(self, same, different, worst_tp, best_fp, step):
        same = sorted(same)
        different = sorted(different)

        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING("Similarity distributions"))
        self.stdout.write(
            f"  {len(same)} same-field pairs (should match), "
            f"{len(different)} different-field pairs (should not)"
        )
        self.stdout.write("")
        self._distribution("same field   ", same)
        self._distribution("different    ", different)

        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING("Where the two overlap"))
        if worst_tp:
            self.stdout.write(f"  hardest true positive  {worst_tp[0]:.3f}  {worst_tp[1]}")
            self.stdout.write(f"    matched: {worst_tp[2][:74]}")
        if best_fp:
            self.stdout.write(f"  worst false positive   {best_fp[0]:.3f}  {best_fp[1]}")
            self.stdout.write(f"    matched: {best_fp[2][:74]}")

        best = self._sweep(same, different, step)

        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING("Threshold sweep"))
        self.stdout.write("  threshold   recall   precision   F1")
        for row in best["table"]:
            marker = "  <-- best F1" if row["threshold"] == best["threshold"] else ""
            self.stdout.write(
                f"     {row['threshold']:.2f}      {row['recall']:.2f}      "
                f"{row['precision']:.2f}     {row['f1']:.2f}{marker}"
            )

        current = settings.SKILL_MATCH_THRESHOLD
        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING("Verdict"))
        self.stdout.write(f"  best separating threshold : {best['threshold']:.2f}  (F1 {best['f1']:.2f})")
        self.stdout.write(f"  SKILL_MATCH_THRESHOLD now : {current:.2f}")

        if abs(best["threshold"] - current) < 0.03:
            self.stdout.write(self.style.SUCCESS("  The configured value is already at the optimum."))
        else:
            self.stdout.write(
                self.style.WARNING(
                    f"  Consider changing SKILL_MATCH_THRESHOLD to {best['threshold']:.2f} "
                    "in config/settings.py."
                )
            )

    def _distribution(self, label, values):
        """Percentiles say more than an average about where a cut should go."""
        if not values:
            self.stdout.write(f"  {label} (no pairs)")
            return

        def percentile(fraction):
            return values[min(int(len(values) * fraction), len(values) - 1)]

        self.stdout.write(
            f"  {label} min {values[0]:.3f} | p10 {percentile(0.10):.3f} | "
            f"median {percentile(0.50):.3f} | p90 {percentile(0.90):.3f} | "
            f"max {values[-1]:.3f}"
        )

    def _sweep(self, same, different, step):
        """
        Try every threshold and score it.

        recall    -- of the pairs that should match, how many do
        precision -- of the pairs that do match, how many should
        F1        -- their harmonic mean, which is what picks the winner,
                     because a threshold of 0 has perfect recall and useless
                     precision while a threshold of 1 has the reverse.
        """
        table, best = [], {"threshold": 0.0, "f1": -1.0}
        value = 0.10

        while value <= 0.80001:
            true_positives = sum(1 for s in same if s >= value)
            false_negatives = len(same) - true_positives
            false_positives = sum(1 for d in different if d >= value)

            recall = true_positives / len(same) if same else 0.0
            precision = (
                true_positives / (true_positives + false_positives)
                if (true_positives + false_positives)
                else 0.0
            )
            f1 = (
                2 * precision * recall / (precision + recall)
                if (precision + recall)
                else 0.0
            )

            row = {
                "threshold": round(value, 2),
                "recall": recall,
                "precision": precision,
                "f1": f1,
                "missed": false_negatives,
                "wrong": false_positives,
            }
            if abs(round(value, 2) * 100) % 5 == 0:
                table.append(row)
            if f1 > best["f1"]:
                best = row

            value += step

        if best not in table:
            table.append(best)
            table.sort(key=lambda r: r["threshold"])

        best["table"] = table
        return best
