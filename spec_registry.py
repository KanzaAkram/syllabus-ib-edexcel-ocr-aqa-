#!/usr/bin/env python3
"""
spec_registry.py
----------------
Canonical registry of every distinct exam-board specification VERSION known for
the top-25 subjects across 2005-2026, transcribed from the brief's
"KNOWN SPEC VERSIONS BY YEAR" tables.

Each record is the source of truth for the NEW year-range convention:

    {board, qual_type, variant, subject, spec_code, alt_codes,
     first_year, last_year, status}

  * qual_type : ALEVEL | AS | GCSE | ELC | IGCSE | IAL | IPRIMARY | ILOWERSEC
                | CAMNAT | DP | MYP | PYP | CP
  * variant   : "" | "A" | "B" | "Linear" | "Modular" | "SL" | "HL"
                | "Old_Suite_2012" | "New_Suite_2022" | "AA" | "AI" | ...
  * last_year : int  OR  "PRESENT"  (still active as of 2026)
  * status    : CURRENT (active in 2026) | LEGACY (retired)

Discovery (the expansion phase) augments this list with PDF/page URLs; the
registry itself carries no URLs so it stays a clean, auditable backbone.
"""

CANON_SUBJECTS = [
    "Mathematics", "Psychology", "Biology", "Chemistry", "Further_Mathematics",
    "History", "Physics", "English_Literature", "English_Language", "Geography",
    "Sociology", "Art_and_Design", "Business_Studies", "Economics", "Computer_Science",
    "Religious_Studies", "Spanish", "French", "Politics", "Physical_Education",
    "Music", "Drama", "Design_and_Technology", "Statistics", "Media_Studies",
]


def rec(board, qual_type, subject, spec_code, first_year, last_year,
        variant="", alt_codes=None, notes=""):
    status = "CURRENT" if (last_year == "PRESENT" or (isinstance(last_year, int) and last_year >= 2025)) else "LEGACY"
    return {
        "board": board, "qual_type": qual_type, "variant": variant,
        "subject": subject, "spec_code": spec_code,
        "alt_codes": alt_codes or [],
        "first_year": first_year, "last_year": last_year,
        "status": status, "notes": notes,
    }


RECORDS = []
A = RECORDS.append

# ============================================================ AQA ============
# --- Mathematics ---
A(rec("AQA", "GCSE", "Mathematics", "3301", 2005, 2011))
A(rec("AQA", "GCSE", "Mathematics", "4360", 2010, 2016))
A(rec("AQA", "GCSE", "Mathematics", "8300", 2017, "PRESENT"))
A(rec("AQA", "ALEVEL", "Mathematics", "5361", 2005, 2016, alt_codes=["5366"]))
A(rec("AQA", "ALEVEL", "Mathematics", "7357", 2017, "PRESENT"))
A(rec("AQA", "GCSE", "Statistics", "4310", 2005, 2016))
A(rec("AQA", "GCSE", "Statistics", "8382", 2017, "PRESENT"))
# --- Further Mathematics ---
A(rec("AQA", "ALEVEL", "Further_Mathematics", "5371", 2005, 2016))
A(rec("AQA", "ALEVEL", "Further_Mathematics", "7367", 2017, "PRESENT"))
# --- Sciences ---
A(rec("AQA", "GCSE", "Biology", "4401", 2011, 2016))
A(rec("AQA", "GCSE", "Biology", "8461", 2017, "PRESENT"))
A(rec("AQA", "ALEVEL", "Biology", "2410", 2005, 2016))
A(rec("AQA", "ALEVEL", "Biology", "7402", 2017, "PRESENT"))
A(rec("AQA", "GCSE", "Chemistry", "4402", 2011, 2016))
A(rec("AQA", "GCSE", "Chemistry", "8462", 2017, "PRESENT"))
A(rec("AQA", "ALEVEL", "Chemistry", "2420", 2005, 2016))
A(rec("AQA", "ALEVEL", "Chemistry", "7405", 2017, "PRESENT"))
A(rec("AQA", "GCSE", "Physics", "4403", 2011, 2016))
A(rec("AQA", "GCSE", "Physics", "8463", 2017, "PRESENT"))
A(rec("AQA", "ALEVEL", "Physics", "2450", 2005, 2016))
A(rec("AQA", "ALEVEL", "Physics", "7408", 2017, "PRESENT"))
# --- English ---
A(rec("AQA", "GCSE", "English_Language", "4700", 2010, 2016))
A(rec("AQA", "GCSE", "English_Language", "8700", 2017, "PRESENT"))
A(rec("AQA", "GCSE", "English_Literature", "4710", 2010, 2016))
A(rec("AQA", "GCSE", "English_Literature", "8702", 2017, "PRESENT"))
A(rec("AQA", "ALEVEL", "English_Language", "2700", 2005, 2016))
A(rec("AQA", "ALEVEL", "English_Language", "7702", 2017, "PRESENT"))
A(rec("AQA", "ALEVEL", "English_Literature", "2710", 2005, 2016))
A(rec("AQA", "ALEVEL", "English_Literature", "7712", 2017, "PRESENT"))
# --- Humanities ---
A(rec("AQA", "GCSE", "History", "4040", 2009, 2016))
A(rec("AQA", "GCSE", "History", "8145", 2017, "PRESENT"))
A(rec("AQA", "ALEVEL", "History", "1041", 2005, 2016))
A(rec("AQA", "ALEVEL", "History", "7042", 2017, "PRESENT"))
A(rec("AQA", "GCSE", "Geography", "4030", 2012, 2016))
A(rec("AQA", "GCSE", "Geography", "8035", 2017, "PRESENT"))
A(rec("AQA", "ALEVEL", "Geography", "2030", 2005, 2016))
A(rec("AQA", "ALEVEL", "Geography", "7037", 2017, "PRESENT"))
A(rec("AQA", "ALEVEL", "Psychology", "2180", 2005, 2016))
A(rec("AQA", "ALEVEL", "Psychology", "7182", 2017, "PRESENT"))
A(rec("AQA", "GCSE", "Sociology", "4190", 2009, 2016))
A(rec("AQA", "GCSE", "Sociology", "8192", 2017, "PRESENT"))
A(rec("AQA", "ALEVEL", "Sociology", "2190", 2005, 2016))
A(rec("AQA", "ALEVEL", "Sociology", "7192", 2017, "PRESENT"))
A(rec("AQA", "ALEVEL", "Economics", "2140", 2005, 2016))
A(rec("AQA", "ALEVEL", "Economics", "7136", 2017, "PRESENT"))
A(rec("AQA", "ALEVEL", "Business_Studies", "1131", 2005, 2016))
A(rec("AQA", "ALEVEL", "Business_Studies", "7132", 2017, "PRESENT"))
A(rec("AQA", "GCSE", "Religious_Studies", "4050", 2009, 2016))
A(rec("AQA", "GCSE", "Religious_Studies", "8062", 2017, "PRESENT"))
A(rec("AQA", "ALEVEL", "Religious_Studies", "2060", 2005, 2016))
A(rec("AQA", "ALEVEL", "Religious_Studies", "7062", 2017, "PRESENT"))
A(rec("AQA", "ALEVEL", "Politics", "2150", 2005, 2016))
A(rec("AQA", "ALEVEL", "Politics", "7152", 2017, "PRESENT"))
A(rec("AQA", "GCSE", "Media_Studies", "4810", 2009, 2016))
A(rec("AQA", "GCSE", "Media_Studies", "8572", 2017, "PRESENT"))
A(rec("AQA", "ALEVEL", "Media_Studies", "2570", 2009, 2016))
A(rec("AQA", "ALEVEL", "Media_Studies", "7572", 2017, "PRESENT"))
# --- Languages ---
A(rec("AQA", "GCSE", "French", "4655", 2009, 2016))
A(rec("AQA", "GCSE", "French", "8658", 2017, "PRESENT"))
A(rec("AQA", "ALEVEL", "French", "2650", 2005, 2016))
A(rec("AQA", "ALEVEL", "French", "7652", 2017, "PRESENT"))
A(rec("AQA", "GCSE", "Spanish", "4695", 2009, 2016))
A(rec("AQA", "GCSE", "Spanish", "8698", 2017, "PRESENT"))
A(rec("AQA", "ALEVEL", "Spanish", "2690", 2005, 2016))
A(rec("AQA", "ALEVEL", "Spanish", "7692", 2017, "PRESENT"))
# --- Arts & Other ---
A(rec("AQA", "GCSE", "Art_and_Design", "4200", 2009, 2016))
A(rec("AQA", "GCSE", "Art_and_Design", "8201", 2017, "PRESENT"))
A(rec("AQA", "ALEVEL", "Art_and_Design", "2200", 2005, 2016))
A(rec("AQA", "ALEVEL", "Art_and_Design", "7201", 2017, "PRESENT"))
A(rec("AQA", "GCSE", "Music", "4270", 2009, 2016))
A(rec("AQA", "GCSE", "Music", "8271", 2017, "PRESENT"))
A(rec("AQA", "ALEVEL", "Music", "2270", 2005, 2016))
A(rec("AQA", "ALEVEL", "Music", "7272", 2017, "PRESENT"))
A(rec("AQA", "GCSE", "Drama", "4240", 2009, 2016))
A(rec("AQA", "GCSE", "Drama", "8261", 2017, "PRESENT"))
A(rec("AQA", "ALEVEL", "Drama", "2240", 2005, 2016))
A(rec("AQA", "ALEVEL", "Drama", "7261", 2017, "PRESENT"))
A(rec("AQA", "GCSE", "Physical_Education", "4890", 2009, 2016))
A(rec("AQA", "GCSE", "Physical_Education", "8582", 2017, "PRESENT"))
A(rec("AQA", "ALEVEL", "Physical_Education", "2580", 2005, 2016))
A(rec("AQA", "ALEVEL", "Physical_Education", "7582", 2017, "PRESENT"))
A(rec("AQA", "GCSE", "Design_and_Technology", "4550", 2009, 2016))
A(rec("AQA", "GCSE", "Design_and_Technology", "8552", 2017, "PRESENT"))
A(rec("AQA", "ALEVEL", "Design_and_Technology", "2550", 2009, 2016))
A(rec("AQA", "ALEVEL", "Design_and_Technology", "7552", 2017, "PRESENT"))
A(rec("AQA", "GCSE", "Computer_Science", "4510", 2012, 2016))
A(rec("AQA", "GCSE", "Computer_Science", "8525", 2017, "PRESENT"))
A(rec("AQA", "ALEVEL", "Computer_Science", "2510", 2010, 2016))
A(rec("AQA", "ALEVEL", "Computer_Science", "7517", 2017, "PRESENT"))
# --- ELC ---
A(rec("AQA", "ELC", "English_Language", "5970", 2017, "PRESENT", notes="Entry Level Certificate"))
A(rec("AQA", "ELC", "Mathematics", "5930", 2017, "PRESENT", notes="Entry Level Certificate"))
A(rec("AQA", "ELC", "Biology", "5960", 2017, "PRESENT", notes="Entry Level Certificate Science"))

# ============================================================ EDEXCEL ========
# --- Mathematics ---
A(rec("Edexcel", "GCSE", "Mathematics", "1380", 2006, 2012))
A(rec("Edexcel", "GCSE", "Mathematics", "1MA1", 2017, "PRESENT"))
A(rec("Edexcel", "ALEVEL", "Mathematics", "8371", 2005, 2012, alt_codes=["8374"]))
A(rec("Edexcel", "ALEVEL", "Mathematics", "9371", 2013, 2016))
A(rec("Edexcel", "ALEVEL", "Mathematics", "9MA0", 2017, "PRESENT"))
A(rec("Edexcel", "IGCSE", "Mathematics", "4400", 2005, 2012, variant="Modular"))
A(rec("Edexcel", "IGCSE", "Mathematics", "4MA0", 2011, 2016, variant="Modular"))
A(rec("Edexcel", "IGCSE", "Mathematics", "4MA1", 2016, "PRESENT", variant="Linear"))
A(rec("Edexcel", "IGCSE", "Further_Mathematics", "4PM0", 2011, 2016, variant="Linear"))
A(rec("Edexcel", "IGCSE", "Further_Mathematics", "4PM1", 2016, "PRESENT", variant="Linear"))
A(rec("Edexcel", "IAL", "Mathematics", "WMA01", 2013, 2018, alt_codes=["WMA02"], notes="modular IAL"))
A(rec("Edexcel", "IAL", "Mathematics", "WMA11", 2018, "PRESENT", alt_codes=["WMA12", "WMA13", "WMA14"]))
A(rec("Edexcel", "GCSE", "Statistics", "1ST0", 2017, "PRESENT"))
# --- Sciences ---
A(rec("Edexcel", "GCSE", "Biology", "2BI01", 2012, 2016))
A(rec("Edexcel", "GCSE", "Biology", "1BI0", 2017, "PRESENT"))
A(rec("Edexcel", "ALEVEL", "Biology", "8BN01", 2008, 2016))
A(rec("Edexcel", "ALEVEL", "Biology", "9BI0", 2017, "PRESENT"))
A(rec("Edexcel", "IGCSE", "Biology", "4BI0", 2009, 2016, variant="Linear"))
A(rec("Edexcel", "IGCSE", "Biology", "4BI1", 2017, "PRESENT", variant="Linear"))
A(rec("Edexcel", "IAL", "Biology", "WBI01", 2014, 2019, alt_codes=["WBI02", "WBI03", "WBI04"]))
A(rec("Edexcel", "IAL", "Biology", "WBI11", 2019, "PRESENT", alt_codes=["WBI12", "WBI13", "WBI14"]))
A(rec("Edexcel", "GCSE", "Chemistry", "2CH01", 2012, 2016))
A(rec("Edexcel", "GCSE", "Chemistry", "1CH0", 2017, "PRESENT"))
A(rec("Edexcel", "ALEVEL", "Chemistry", "8CH01", 2008, 2016))
A(rec("Edexcel", "ALEVEL", "Chemistry", "9CH0", 2017, "PRESENT"))
A(rec("Edexcel", "IGCSE", "Chemistry", "4CH0", 2009, 2016, variant="Linear"))
A(rec("Edexcel", "IGCSE", "Chemistry", "4CH1", 2017, "PRESENT", variant="Linear"))
A(rec("Edexcel", "IAL", "Chemistry", "WCH01", 2014, 2019, alt_codes=["WCH02", "WCH03", "WCH04"]))
A(rec("Edexcel", "IAL", "Chemistry", "WCH11", 2019, "PRESENT", alt_codes=["WCH12", "WCH13", "WCH14"]))
A(rec("Edexcel", "GCSE", "Physics", "2PH01", 2012, 2016))
A(rec("Edexcel", "GCSE", "Physics", "1PH0", 2017, "PRESENT"))
A(rec("Edexcel", "ALEVEL", "Physics", "8PH01", 2008, 2016))
A(rec("Edexcel", "ALEVEL", "Physics", "9PH0", 2017, "PRESENT"))
A(rec("Edexcel", "IGCSE", "Physics", "4PH0", 2009, 2016, variant="Linear"))
A(rec("Edexcel", "IGCSE", "Physics", "4PH1", 2017, "PRESENT", variant="Linear"))
A(rec("Edexcel", "IAL", "Physics", "WPH01", 2014, 2019, alt_codes=["WPH02", "WPH03", "WPH04"]))
A(rec("Edexcel", "IAL", "Physics", "WPH11", 2019, "PRESENT", alt_codes=["WPH12", "WPH13", "WPH14"]))
# --- English ---
A(rec("Edexcel", "GCSE", "English_Language", "2EN01", 2012, 2016))
A(rec("Edexcel", "GCSE", "English_Language", "1EN0", 2017, "PRESENT"))
A(rec("Edexcel", "GCSE", "English_Literature", "2ET01", 2012, 2016))
A(rec("Edexcel", "GCSE", "English_Literature", "1ET0", 2017, "PRESENT"))
A(rec("Edexcel", "ALEVEL", "English_Language", "8EN01", 2008, 2016))
A(rec("Edexcel", "ALEVEL", "English_Language", "9EN0", 2017, "PRESENT"))
A(rec("Edexcel", "ALEVEL", "English_Literature", "8ET01", 2008, 2016))
A(rec("Edexcel", "ALEVEL", "English_Literature", "9ET0", 2017, "PRESENT"))
A(rec("Edexcel", "IGCSE", "English_Language", "4EA0", 2011, 2016, variant="Linear"))
A(rec("Edexcel", "IGCSE", "English_Language", "4EA1", 2017, "PRESENT", variant="Linear"))
A(rec("Edexcel", "IGCSE", "English_Literature", "4ET0", 2011, 2016, variant="Linear"))
A(rec("Edexcel", "IGCSE", "English_Literature", "4ET1", 2017, "PRESENT", variant="Linear"))
# --- Humanities & Social Sciences ---
A(rec("Edexcel", "ALEVEL", "History", "8HI01", 2008, 2016))
A(rec("Edexcel", "ALEVEL", "History", "9HI0", 2017, "PRESENT"))
A(rec("Edexcel", "GCSE", "History", "2HI01", 2012, 2016))
A(rec("Edexcel", "GCSE", "History", "1HI0", 2017, "PRESENT"))
A(rec("Edexcel", "IGCSE", "History", "4HI0", 2013, 2016, variant="Linear"))
A(rec("Edexcel", "IGCSE", "History", "4HI1", 2017, "PRESENT", variant="Linear"))
A(rec("Edexcel", "ALEVEL", "Geography", "8GE01", 2008, 2016))
A(rec("Edexcel", "ALEVEL", "Geography", "9GE0", 2017, "PRESENT"))
A(rec("Edexcel", "GCSE", "Geography", "2GE01", 2012, 2016))
A(rec("Edexcel", "GCSE", "Geography", "1GA0", 2017, "PRESENT", notes="Geography A"))
A(rec("Edexcel", "IGCSE", "Geography", "4GE0", 2013, 2016, variant="Linear"))
A(rec("Edexcel", "IGCSE", "Geography", "4GE1", 2017, "PRESENT", variant="Linear"))
A(rec("Edexcel", "ALEVEL", "Economics", "8EC01", 2008, 2016))
A(rec("Edexcel", "ALEVEL", "Economics", "9EC0", 2017, "PRESENT"))
A(rec("Edexcel", "IGCSE", "Economics", "4EC0", 2011, 2016, variant="Linear"))
A(rec("Edexcel", "IGCSE", "Economics", "4EC1", 2017, "PRESENT", variant="Linear"))
A(rec("Edexcel", "ALEVEL", "Business_Studies", "8BS01", 2008, 2016))
A(rec("Edexcel", "ALEVEL", "Business_Studies", "9BS0", 2017, "PRESENT"))
A(rec("Edexcel", "GCSE", "Business_Studies", "2BS01", 2012, 2016))
A(rec("Edexcel", "GCSE", "Business_Studies", "1BS0", 2017, "PRESENT"))
A(rec("Edexcel", "IGCSE", "Business_Studies", "4BS0", 2011, 2016, variant="Linear"))
A(rec("Edexcel", "IGCSE", "Business_Studies", "4BS1", 2017, "PRESENT", variant="Linear"))
A(rec("Edexcel", "ALEVEL", "Psychology", "8PS01", 2008, 2016))
A(rec("Edexcel", "ALEVEL", "Psychology", "9PS0", 2017, "PRESENT"))
A(rec("Edexcel", "ALEVEL", "Sociology", "8SO01", 2008, 2016))
A(rec("Edexcel", "ALEVEL", "Sociology", "9SO0", 2017, "PRESENT"))
A(rec("Edexcel", "ALEVEL", "Religious_Studies", "8RS01", 2008, 2016))
A(rec("Edexcel", "ALEVEL", "Religious_Studies", "9RS0", 2017, "PRESENT"))
A(rec("Edexcel", "GCSE", "Religious_Studies", "2RS01", 2012, 2016))
A(rec("Edexcel", "GCSE", "Religious_Studies", "1RS0", 2017, "PRESENT"))
A(rec("Edexcel", "ALEVEL", "Media_Studies", "9MD0", 2017, "PRESENT"))
A(rec("Edexcel", "ALEVEL", "Politics", "8GP01", 2008, 2016, notes="Government & Politics"))
A(rec("Edexcel", "ALEVEL", "Politics", "9PL0", 2017, "PRESENT"))
# --- Languages ---
A(rec("Edexcel", "ALEVEL", "French", "8FR01", 2008, 2016))
A(rec("Edexcel", "ALEVEL", "French", "9FR0", 2017, "PRESENT"))
A(rec("Edexcel", "GCSE", "French", "2FR01", 2012, 2016))
A(rec("Edexcel", "GCSE", "French", "1FR0", 2017, "PRESENT"))
A(rec("Edexcel", "IGCSE", "French", "4FR0", 2011, 2016, variant="Linear"))
A(rec("Edexcel", "IGCSE", "French", "4FR1", 2017, "PRESENT", variant="Linear"))
A(rec("Edexcel", "IAL", "French", "WFR01", 2014, "PRESENT"))
A(rec("Edexcel", "ALEVEL", "Spanish", "8SP01", 2008, 2016))
A(rec("Edexcel", "ALEVEL", "Spanish", "9SP0", 2017, "PRESENT"))
A(rec("Edexcel", "GCSE", "Spanish", "2SP01", 2012, 2016))
A(rec("Edexcel", "GCSE", "Spanish", "1SP0", 2017, "PRESENT"))
A(rec("Edexcel", "IGCSE", "Spanish", "4SP0", 2011, 2016, variant="Linear"))
A(rec("Edexcel", "IGCSE", "Spanish", "4SP1", 2017, "PRESENT", variant="Linear"))
A(rec("Edexcel", "IAL", "Spanish", "WSP01", 2014, "PRESENT"))
# --- Arts & Other ---
A(rec("Edexcel", "ALEVEL", "Art_and_Design", "8AR01", 2008, 2016))
A(rec("Edexcel", "ALEVEL", "Art_and_Design", "9AR0", 2017, "PRESENT"))
A(rec("Edexcel", "IGCSE", "Art_and_Design", "4AR0", 2011, 2016, variant="Linear"))
A(rec("Edexcel", "IGCSE", "Art_and_Design", "4AR1", 2017, "PRESENT", variant="Linear"))
A(rec("Edexcel", "ALEVEL", "Music", "8MU01", 2008, 2016))
A(rec("Edexcel", "ALEVEL", "Music", "9MU0", 2017, "PRESENT"))
A(rec("Edexcel", "IGCSE", "Music", "4MU0", 2011, 2016, variant="Linear"))
A(rec("Edexcel", "IGCSE", "Music", "4MU1", 2017, "PRESENT", variant="Linear"))
A(rec("Edexcel", "ALEVEL", "Drama", "8DR01", 2008, 2016))
A(rec("Edexcel", "ALEVEL", "Drama", "9DR0", 2017, "PRESENT"))
A(rec("Edexcel", "IGCSE", "Drama", "4DR0", 2011, 2016, variant="Linear"))
A(rec("Edexcel", "IGCSE", "Drama", "4DR1", 2017, "PRESENT", variant="Linear"))
A(rec("Edexcel", "ALEVEL", "Physical_Education", "8PE01", 2008, 2016))
A(rec("Edexcel", "ALEVEL", "Physical_Education", "9PE0", 2017, "PRESENT"))
A(rec("Edexcel", "ALEVEL", "Design_and_Technology", "8DE01", 2008, 2016))
A(rec("Edexcel", "ALEVEL", "Design_and_Technology", "9DE0", 2017, "PRESENT"))
A(rec("Edexcel", "ALEVEL", "Computer_Science", "8CP01", 2012, 2016))
A(rec("Edexcel", "ALEVEL", "Computer_Science", "9CP0", 2017, "PRESENT"))
A(rec("Edexcel", "GCSE", "Computer_Science", "2CP01", 2012, 2016))
A(rec("Edexcel", "GCSE", "Computer_Science", "1CP0", 2017, "PRESENT"))
A(rec("Edexcel", "IGCSE", "Computer_Science", "4CP0", 2013, 2016, variant="Linear"))
A(rec("Edexcel", "IGCSE", "Computer_Science", "4CP1", 2017, "PRESENT", variant="Linear"))
# --- iPrimary (2018-present) ---
A(rec("Edexcel", "IPRIMARY", "Mathematics", "JMA11", 2018, "PRESENT"))
A(rec("Edexcel", "IPRIMARY", "English_Language", "JEH11", 2018, "PRESENT", notes="English"))
A(rec("Edexcel", "IPRIMARY", "Biology", "JSC11", 2018, "PRESENT", notes="Science"))
A(rec("Edexcel", "IPRIMARY", "Computer_Science", "JCP11", 2018, "PRESENT", notes="Computing"))
# --- iLowerSecondary (2018-present) ---
A(rec("Edexcel", "ILOWERSEC", "Mathematics", "LMA11", 2018, "PRESENT"))
A(rec("Edexcel", "ILOWERSEC", "English_Language", "LEH11", 2018, "PRESENT", notes="English"))
A(rec("Edexcel", "ILOWERSEC", "Biology", "LSC11", 2018, "PRESENT", notes="Science"))
A(rec("Edexcel", "ILOWERSEC", "Computer_Science", "LCP11", 2018, "PRESENT", notes="Computing"))

# ============================================================ OCR =============
# --- Mathematics ---
A(rec("OCR", "GCSE", "Mathematics", "J567", 2012, 2016, variant="B"))
A(rec("OCR", "GCSE", "Mathematics", "J560", 2015, "PRESENT", variant="A"))
A(rec("OCR", "ALEVEL", "Mathematics", "H240", 2017, "PRESENT", variant="A", alt_codes=["H230"]))
A(rec("OCR", "ALEVEL", "Mathematics", "4721", 2005, 2016, variant="MEI", notes="MEI units 4721-4729"))
A(rec("OCR", "ALEVEL", "Further_Mathematics", "H245", 2017, "PRESENT", alt_codes=["H235"]))
# --- Sciences ---
A(rec("OCR", "ALEVEL", "Biology", "F211", 2008, 2016, variant="A", notes="units F211-F216"))
A(rec("OCR", "ALEVEL", "Biology", "H420", 2017, "PRESENT", variant="A", alt_codes=["H020"]))
A(rec("OCR", "ALEVEL", "Biology", "H422", 2017, "PRESENT", variant="B", alt_codes=["H021"]))
A(rec("OCR", "ALEVEL", "Chemistry", "F321", 2008, 2016, variant="A", notes="units F321-F326"))
A(rec("OCR", "ALEVEL", "Chemistry", "H432", 2017, "PRESENT", variant="A", alt_codes=["H032"]))
A(rec("OCR", "ALEVEL", "Chemistry", "H433", 2017, "PRESENT", variant="B", alt_codes=["H033"]))
A(rec("OCR", "ALEVEL", "Physics", "F321P", 2008, 2016, variant="A", notes="units F321-F325 (Physics A)"))
A(rec("OCR", "ALEVEL", "Physics", "H557", 2017, "PRESENT", variant="A", alt_codes=["H157"]))
A(rec("OCR", "ALEVEL", "Physics", "H558", 2017, "PRESENT", variant="B", alt_codes=["H158"]))
A(rec("OCR", "GCSE", "Biology", "J247", 2017, "PRESENT", variant="A"))
A(rec("OCR", "GCSE", "Biology", "J257", 2017, "PRESENT", variant="B"))
A(rec("OCR", "GCSE", "Chemistry", "J248", 2017, "PRESENT", variant="A"))
A(rec("OCR", "GCSE", "Chemistry", "J258", 2017, "PRESENT", variant="B"))
A(rec("OCR", "GCSE", "Physics", "J249", 2017, "PRESENT", variant="A"))
A(rec("OCR", "GCSE", "Physics", "J259", 2017, "PRESENT", variant="B"))
# --- Humanities ---
A(rec("OCR", "ALEVEL", "History", "Y100", 2015, "PRESENT", notes="History A; suite Y100-Y320"))
A(rec("OCR", "ALEVEL", "History", "F961", 2008, 2016, notes="units F961-F966"))
A(rec("OCR", "GCSE", "History", "J410", 2016, "PRESENT", variant="A"))
A(rec("OCR", "GCSE", "History", "J417", 2012, 2016, variant="B"))
A(rec("OCR", "ALEVEL", "Geography", "H481", 2016, "PRESENT", alt_codes=["H081"]))
A(rec("OCR", "ALEVEL", "Geography", "F761", 2008, 2016, notes="units F761-F767"))
A(rec("OCR", "GCSE", "Geography", "J384", 2016, "PRESENT", variant="B"))
A(rec("OCR", "GCSE", "Geography", "J383", 2016, "PRESENT", variant="A"))
A(rec("OCR", "ALEVEL", "Economics", "H460", 2015, "PRESENT", alt_codes=["H060"]))
A(rec("OCR", "ALEVEL", "Economics", "F581", 2008, 2016, notes="units F581-F585"))
A(rec("OCR", "ALEVEL", "Business_Studies", "H431", 2015, "PRESENT", alt_codes=["H031"]))
A(rec("OCR", "ALEVEL", "Business_Studies", "F291", 2009, 2016, notes="units F291-F297"))
A(rec("OCR", "GCSE", "Business_Studies", "J204", 2017, "PRESENT"))
A(rec("OCR", "ALEVEL", "Psychology", "H567", 2015, "PRESENT", alt_codes=["H067"]))
A(rec("OCR", "ALEVEL", "Psychology", "F221", 2008, 2016, notes="units F221-F215"))
A(rec("OCR", "GCSE", "Psychology", "J203", 2017, "PRESENT"))
A(rec("OCR", "ALEVEL", "Sociology", "H580", 2015, "PRESENT", alt_codes=["H080"]))
A(rec("OCR", "ALEVEL", "Sociology", "F671", 2008, 2016, notes="units F671-F679"))
A(rec("OCR", "ALEVEL", "Religious_Studies", "H573", 2016, "PRESENT", alt_codes=["H173"]))
A(rec("OCR", "ALEVEL", "Religious_Studies", "G571", 2009, 2016, notes="units G571-G582"))
A(rec("OCR", "GCSE", "Religious_Studies", "J625", 2016, "PRESENT"))
A(rec("OCR", "GCSE", "Religious_Studies", "J621", 2012, 2016, variant="B"))
A(rec("OCR", "ALEVEL", "Media_Studies", "H409", 2017, "PRESENT", alt_codes=["H009"]))
A(rec("OCR", "GCSE", "Media_Studies", "J200", 2017, "PRESENT"))
A(rec("OCR", "ALEVEL", "Politics", "H410", 2017, "PRESENT", alt_codes=["H010"]))
# --- Languages ---
A(rec("OCR", "ALEVEL", "French", "H455", 2016, "PRESENT", alt_codes=["H055"]))
A(rec("OCR", "ALEVEL", "French", "F701", 2008, 2016, notes="units F701-F704"))
A(rec("OCR", "GCSE", "French", "J242", 2016, "PRESENT"))
A(rec("OCR", "ALEVEL", "Spanish", "H453", 2016, "PRESENT", alt_codes=["H053"]))
A(rec("OCR", "GCSE", "Spanish", "J243", 2016, "PRESENT"))
# --- Arts & Other ---
A(rec("OCR", "ALEVEL", "English_Literature", "H472", 2015, "PRESENT", alt_codes=["H072"]))
A(rec("OCR", "ALEVEL", "English_Literature", "F661", 2008, 2016, notes="units F661-F664"))
A(rec("OCR", "ALEVEL", "English_Language", "H470", 2015, "PRESENT", alt_codes=["H070"]))
A(rec("OCR", "ALEVEL", "English_Language", "F651", 2008, 2016, notes="units F651-F654"))
A(rec("OCR", "GCSE", "English_Literature", "J352", 2015, "PRESENT"))
A(rec("OCR", "GCSE", "English_Language", "J351", 2015, "PRESENT"))
A(rec("OCR", "ALEVEL", "Art_and_Design", "H600", 2017, "PRESENT", notes="suite H600-H606"))
A(rec("OCR", "ALEVEL", "Art_and_Design", "F610", 2009, 2016, notes="units F610-F619"))
A(rec("OCR", "GCSE", "Art_and_Design", "J170", 2017, "PRESENT", notes="suite J170-J176"))
A(rec("OCR", "ALEVEL", "Music", "H543", 2016, "PRESENT", alt_codes=["H043"]))
A(rec("OCR", "ALEVEL", "Music", "F661M", 2009, 2016, notes="legacy Music units"))
A(rec("OCR", "GCSE", "Music", "J536", 2016, "PRESENT"))
A(rec("OCR", "ALEVEL", "Drama", "H459", 2016, "PRESENT", alt_codes=["H059"], notes="Drama & Theatre"))
A(rec("OCR", "ALEVEL", "Drama", "F641", 2009, 2016, notes="units F641-F645"))
A(rec("OCR", "GCSE", "Drama", "J316", 2017, "PRESENT"))
A(rec("OCR", "ALEVEL", "Physical_Education", "H555", 2016, "PRESENT", alt_codes=["H155"]))
A(rec("OCR", "ALEVEL", "Physical_Education", "F453", 2009, 2016, notes="units F451-F454"))
A(rec("OCR", "GCSE", "Physical_Education", "J587", 2017, "PRESENT"))
A(rec("OCR", "ALEVEL", "Design_and_Technology", "H404", 2017, "PRESENT", alt_codes=["H004"]))
A(rec("OCR", "GCSE", "Design_and_Technology", "J310", 2017, "PRESENT"))
A(rec("OCR", "ALEVEL", "Computer_Science", "H446", 2016, "PRESENT", alt_codes=["H046"]))
A(rec("OCR", "ALEVEL", "Computer_Science", "F452", 2012, 2016, notes="Computing units F451-F454"))
A(rec("OCR", "GCSE", "Computer_Science", "J277", 2020, "PRESENT"))
A(rec("OCR", "GCSE", "Computer_Science", "J276", 2016, 2020))
# --- Cambridge Nationals (two suites) ---
A(rec("OCR", "CAMNAT", "Computer_Science", "J800", 2012, 2022, variant="Old_Suite_2012", notes="IT"))
A(rec("OCR", "CAMNAT", "Computer_Science", "J836", 2022, "PRESENT", variant="New_Suite_2022", notes="IT"))
A(rec("OCR", "CAMNAT", "Media_Studies", "J834", 2022, "PRESENT", variant="New_Suite_2022", notes="Creative iMedia"))
A(rec("OCR", "CAMNAT", "Business_Studies", "J837", 2022, "PRESENT", variant="New_Suite_2022", notes="Business"))
A(rec("OCR", "CAMNAT", "Physical_Education", "J832", 2022, "PRESENT", variant="New_Suite_2022", notes="Sport Science"))

# ============================================================ IB ==============
# DP version generations: 2009, 2014, 2019, 2023 first-assessment cohorts.
# Variant SL/HL is recorded; many guides are combined SL+HL (variant "SL_HL").
def ib_dp(subject, gens, variant="SL_HL", notes=""):
    # gens: list of (first_year, last_year)
    for fy, ly in gens:
        A(rec("IB", "DP", subject, "NA", fy, ly, variant=variant, notes=notes))

# Group 4 sciences — guide generations 2009-2015, 2016-2024(2025), 2025-present
ib_dp("Biology", [(2009, 2015), (2016, 2024), (2025, "PRESENT")], notes="Biology -> Biological Sciences 2025")
ib_dp("Chemistry", [(2009, 2015), (2016, 2024), (2025, "PRESENT")])
ib_dp("Physics", [(2009, 2015), (2016, 2024), (2025, "PRESENT")])
ib_dp("Computer_Science", [(2014, 2021), (2014, "PRESENT")])
# Group 3
ib_dp("Psychology", [(2011, 2018), (2019, "PRESENT")])
ib_dp("History", [(2010, 2016), (2017, "PRESENT")])
ib_dp("Geography", [(2009, 2016), (2017, "PRESENT")])
ib_dp("Economics", [(2011, 2021), (2022, "PRESENT")])
ib_dp("Business_Studies", [(2014, 2023), (2024, "PRESENT")], notes="Business Management")
ib_dp("Politics", [(2017, "PRESENT")], notes="Global Politics")
# Group 5 Mathematics (post-2019 AA/AI split; pre-2019 single courses)
A(rec("IB", "DP", "Mathematics", "NA", 2014, 2020, variant="SL", notes="Mathematics SL (pre-2019 course)"))
A(rec("IB", "DP", "Mathematics", "NA", 2014, 2020, variant="HL", notes="Mathematics HL (pre-2019 course)"))
A(rec("IB", "DP", "Mathematics", "NA", 2021, "PRESENT", variant="AA", notes="Analysis & Approaches SL+HL"))
A(rec("IB", "DP", "Mathematics", "NA", 2021, "PRESENT", variant="AI", notes="Applications & Interpretation SL+HL"))
A(rec("IB", "DP", "Further_Mathematics", "NA", 2014, 2020, variant="HL", notes="Further Mathematics HL (retired 2020)"))
# Group 1 English
ib_dp("English_Literature", [(2011, 2020), (2021, "PRESENT")], notes="English A: Literature")
ib_dp("English_Language", [(2011, 2020), (2021, "PRESENT")], notes="English A: Language & Literature")
# Group 2 Languages
ib_dp("French", [(2011, 2019), (2020, "PRESENT")], notes="French B")
ib_dp("Spanish", [(2011, 2019), (2020, "PRESENT")], notes="Spanish B")
# Group 6 Arts
ib_dp("Music", [(2011, 2021), (2022, "PRESENT")])
ib_dp("Drama", [(2009, 2015), (2016, "PRESENT")], notes="Theatre")
ib_dp("Art_and_Design", [(2009, 2015), (2016, "PRESENT")], notes="Visual Arts")
ib_dp("Media_Studies", [(2009, 2018), (2019, "PRESENT")], notes="Film")
# MYP / PYP frameworks
A(rec("IB", "MYP", "Mathematics", "NA", 2014, "PRESENT", notes="MYP subject guide (2014, updated 2020)"))
A(rec("IB", "PYP", "Mathematics", "NA", 2018, "PRESENT", notes="PYP enhanced framework 2018"))
A(rec("IB", "PYP", "Mathematics", "NA", 2009, 2017, notes="PYP 2009 framework"))


def by_subject():
    out = {s: [] for s in CANON_SUBJECTS}
    for r in RECORDS:
        out.setdefault(r["subject"], []).append(r)
    return out


if __name__ == "__main__":
    import collections, json
    print("total records:", len(RECORDS))
    bq = collections.Counter((r["board"], r["qual_type"]) for r in RECORDS)
    for k in sorted(bq, key=lambda x: (x[0], x[1])):
        print(f"  {k[0]:8} {k[1]:10} {bq[k]}")
    st = collections.Counter(r["status"] for r in RECORDS)
    print("status:", dict(st))
    subj = collections.Counter(r["subject"] for r in RECORDS)
    missing = [s for s in CANON_SUBJECTS if subj[s] == 0]
    print("subjects with zero records:", missing)
    json.dump(RECORDS, open("spec_registry.json", "w", encoding="utf-8"), indent=1)
    print("wrote spec_registry.json")
