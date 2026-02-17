name: Process RAP Tornado Data

on:
  workflow_dispatch:  # Only manual or self-triggered runs

permissions:
  contents: write

jobs:
  process_rap:
    runs-on: ubuntu-latest

    steps:

      # ----------------------------
      # 1. Checkout repo
      # ----------------------------
      - name: Checkout repo
        uses: actions/checkout@v4

      # ----------------------------
      # 2. Setup Python
      # ----------------------------
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      # ----------------------------
      # 3. Install system + Python deps
      # ----------------------------
      - name: Install dependencies
        run: |
          sudo apt-get update
          sudo apt-get install -y \
            libeccodes-dev \
            gdal-bin \
            libgdal-dev

          pip install --upgrade pip

          pip install \
            pygrib \
            numpy \
            xarray \
            geopandas \
            pyproj \
            shapely \
            fiona \
            requests

      # ----------------------------
      # 4. Process RAP
      # ----------------------------
      - name: Process RAP data
        run: |
          python scripts/process_rap.py

      # ----------------------------
      # 5. Convert borders
      # ----------------------------
      - name: Convert borders to LCC
        run: |
          python scripts/convert_borders_to_lcc.py

      # ----------------------------
      # 6. Commit + push outputs
      # ----------------------------
      - name: Commit and push data
        run: |
          git config user.name "github-actions"
          git config user.email "actions@github.com"

          git add map/data

          git commit -m "Auto update RAP data" || echo "Nothing to commit"

          git push

      # ----------------------------
      # 7. Sleep until next :55 UTC
      # ----------------------------
      - name: Wait until next :55 UTC
        run: |
          now_min=$(date -u +%M)
          minute=${now_min#0}
          # Calculate minutes until :55
          wait_minutes=$(( (55 - minute + 60) % 60 ))
          echo "Sleeping for $wait_minutes minutes until :55 UTC..."
          sleep $((wait_minutes * 60))

      # ----------------------------
      # 8. Self-trigger workflow
      # ----------------------------
      - name: Self-trigger workflow
        uses: peter-evans/workflow-dispatch@v2
        with:
          token: ${{ secrets.GITHUB_TOKEN }}
          repository: ${{ github.repository }}
          workflow: process_rap.yml
          ref: main
