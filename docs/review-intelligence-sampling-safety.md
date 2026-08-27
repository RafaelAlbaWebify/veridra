# Review Intelligence sampling safety

VERIDRA deliberately captures stratified Google review evidence using newest, lowest-rating and highest-rating samples. The merged review rows are useful for evidence inspection and AI theme analysis, but they are not a random or complete sample of a business's review population.

The safe statistics contract is therefore:

- recency counts are calculated only from rows captured after explicitly selecting `newest`;
- owner-response rate associated with recency is scoped to the `newest` sample;
- negative-review response rate is calculated only from negative rows in the `lowest` sample;
- highest-rating rows are retained for positive-theme evidence only;
- review velocity, overall owner-response rate and overall rating distribution are suppressed because the stratified sample cannot support population-level claims;
- if the newest sort was unavailable and the visible default ordering was used, newest/recency statistics are unavailable rather than inferred.

Raw review evidence remains read-only. This layer performs no persistence, outreach, sentiment classification or AI interpretation.
