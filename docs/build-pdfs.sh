#!/usr/bin/env bash
# Dependencies (Ubuntu/Debian):
#   sudo apt-get install -y pandoc texlive-latex-extra texlive-fonts-recommended
set -e

cd "$(dirname "$0")"

PANDOC_OPTS="--include-in-header=pdf-header.tex --pdf-engine=pdflatex -V geometry:margin=2cm -V papersize=a4"

FILES=(workflow_en workflow_fr manual_en manual_fr)

for name in "${FILES[@]}"; do
    echo "Building ${name}.pdf..."
    pandoc "${name}.md" -o "${name}.pdf" $PANDOC_OPTS
done

echo "Done."
