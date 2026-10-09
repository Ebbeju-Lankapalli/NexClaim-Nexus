#!/bin/sh

apt-get update && apt-get install -y tesseract-ocr poppler-utils
pip3 install -r requirements.txt

pytest --junitxml=testreport.xml --cov --cov-report xml:coverage.xml --cov-report=html:coverage_report