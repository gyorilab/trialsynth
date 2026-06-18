"""Centralized pystow path constants for the extract pipeline."""
import pystow

TRIALSYNTH_BASE = pystow.module("trialsynth")
CONTENT_TXT_DIR = TRIALSYNTH_BASE.module("content", "txt")
RESULTS_DIR = TRIALSYNTH_BASE.module("results")
RESULTS_RAW_DIR = RESULTS_DIR.module("raw")
RESULTS_GROUNDED_DIR = RESULTS_DIR.module("grounded")
CLINICALTRIALS_DIR = TRIALSYNTH_BASE.module("clinicaltrials")
XML_DIR = CLINICALTRIALS_DIR.module("xml")
