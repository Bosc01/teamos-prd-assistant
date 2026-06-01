# teamos-prd-assistant

A simple local Python pipeline that ingests Terraform-related Reddit posts and converts them into PRD-ready product insights.

## Project structure

- `src/ingest.py` fetches Reddit posts from `r/terraform`
- `src/process.py` classifies, summarizes, and tags each post
- `src/aggregate.py` groups similar issues and counts frequency
- `src/generate_prd.py` creates a markdown output for PRD review
- `data/` stores raw and processed JSON files
- `output/` stores final markdown outputs
- `prompts/` stores prompt templates for classification, summarization, and PRD generation

## Run the pipeline

From the repository root:

```bash
python src/ingest.py
python src/process.py
python src/aggregate.py
python src/generate_prd.py
```

Generated files:

- `data/raw/reddit_posts.json`
- `data/processed/processed_posts.json`
- `data/processed/aggregated_insights.json`
- `output/prd_insights.md`

## Notes

- `src/ingest.py` uses Reddit's public JSON endpoint when available and falls back to `data/raw/sample_reddit_posts.json` if the network is unavailable.
- `src/process.py` can call an OpenAI-compatible chat completion endpoint when `TEAMOS_OPENAI_API_KEY` is set; otherwise it uses local heuristics so the pipeline remains runnable without extra services.
- All pipeline data is stored locally as JSON, and the final insight summary is written as markdown.
