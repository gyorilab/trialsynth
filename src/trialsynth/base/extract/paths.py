"""Centralized pystow path constants for the extract pipeline."""
import pystow

CONTENT_TXT_DIR = pystow.module("trialsynth", "content", "txt").base
RESULTS_RAW_DIR = pystow.join("trialsynth", "results", "raw")
RESULTS_GROUNDED_DIR = pystow.join("trialsynth", "results", "grounded")
CLINICALTRIALS_DIR = pystow.module("trialsynth", "clinicaltrials").base
XML_DIR = pystow.module("trialsynth", "clinicaltrials", "xml").base
