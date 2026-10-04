# %% [markdown]
# Survey response analysis

# %%
import pandas as pd
from IPython.display import Markdown, display

from survey_responce import (
	average_response_size_by_model,
	load_responses,
	rank_llms_by_category_pl,
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
rankings_by_category = rank_llms_by_category_pl(responses, survey_path)
for category, rankings in rankings_by_category.items():
	display(Markdown(f"### {category}"))
	display(pd.DataFrame(rankings).set_index("rank"))

# %% [markdown]
# Average response size by model

# %%
average_response_sizes = average_response_size_by_model(output_dir)
average_response_sizes
