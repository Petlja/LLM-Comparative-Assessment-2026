# %% [markdown]
# Survey response analysis

# %%
from survey_responce import (
	average_response_size_by_model,
	load_responses,
	rank_llms_by_category,
)

# %%
output_dir = "../eval/output"
responses_path = "../eval/output/survey-test-responces.json"
survey_path = "../eval/output/survey.json"

responses = load_responses(responses_path)
len(responses)

# %% [markdown]
# Plackett-Luce rankings by category

# %%
rankings_by_category = rank_llms_by_category(responses, survey_path)
rankings_by_category

# %% [markdown]
# Average response size by model

# %%
average_response_sizes = average_response_size_by_model(output_dir)
average_response_sizes
