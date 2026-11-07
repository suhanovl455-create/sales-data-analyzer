#!/bin/zsh
cd "${0:A:h}"
if [[ ! -x .venv/bin/python ]]; then
    echo 'Сначала установите зависимости по инструкции в README.md.'
    read '?Нажмите Enter, чтобы закрыть окно.'
    exit 1
fi
exec .venv/bin/python -m streamlit run app.py
