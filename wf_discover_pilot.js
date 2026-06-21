export const meta = {
  name: 'discover-pilot-urls',
  description: 'Find + verify official spec PDF/landing URLs for missing Biology & Mathematics versions (pilot)',
  phases: [{ title: 'Discover', detail: 'one web-research agent per board (AQA, Edexcel, OCR, IB)' }],
}

const SCHEMA = {
  type: 'object',
  additionalProperties: false,
  properties: {
    targets: {
      type: 'array',
      items: {
        type: 'object',
        additionalProperties: false,
        properties: {
          board: { type: 'string' },
          qual_type: { type: 'string' },
          variant: { type: 'string' },
          subject: { type: 'string' },
          spec_code: { type: 'string' },
          first_year: { type: 'string' },
          last_year: { type: 'string' },
          status: { type: 'string' },
          pdf_url: { type: 'string', description: 'direct https URL ending .pdf, or empty' },
          page_url: { type: 'string', description: 'official spec landing page that links the PDF, or empty' },
          verified: { type: 'boolean', description: 'true ONLY if you fetched the pdf_url and confirmed it is a real PDF spec' },
          notes: { type: 'string' },
        },
        required: ['board', 'qual_type', 'variant', 'subject', 'spec_code',
                   'first_year', 'last_year', 'status', 'pdf_url', 'page_url', 'verified', 'notes'],
      },
    },
  },
  required: ['targets'],
}

const COMMON = `
You are a meticulous research agent locating OFFICIAL exam-board specification (syllabus) PDFs.
Rules:
- Return ONE entry per target version listed. Keep board/qual_type/variant/subject/spec_code/first_year/last_year/status EXACTLY as given.
- Use WebSearch to locate the official spec page, then WebFetch the candidate PDF URL to CONFIRM it is a real PDF specification (not a sample-assessment, mark scheme, past paper, or HTML page).
- pdf_url = a direct https link ending in .pdf on the OFFICIAL domain. page_url = the official spec landing page that links the spec PDF.
- Set verified=true ONLY if you fetched the pdf_url and it is genuinely the specification PDF. Otherwise verified=false but still give your best pdf_url and/or page_url.
- If a version genuinely does not exist / is not offered, set pdf_url="" page_url="" verified=false and notes="NOT_OFFERED: <reason>".
- NEVER invent a URL you did not find or confirm. An empty string is better than a guess.
Return ONLY the structured object.
`

const AQA = `${COMMON}
BOARD: AQA. Official PDFs live at https://filestore.aqa.org.uk/resources/<subject-slug>/specifications/AQA-<CODE>-SP-<YEAR>.PDF
(subject slugs e.g. biology, mathematics). Legacy (pre-2017) specs are often NOT on the filestore — check the AQA subject page "Specification at a glance / Past specifications" and the Internet Archive (web.archive.org) for old PDFs.
TARGETS:
- AQA GCSE Biology 4401 (2011->2016 LEGACY)
- AQA ELC Biology(Science) 5960 (2017->PRESENT CURRENT)
- AQA GCSE Mathematics 3301 (2005->2011 LEGACY)
- AQA GCSE Mathematics 4360 (2010->2016 LEGACY)
- AQA ALEVEL Mathematics 5361 (2005->2016 LEGACY)
- AQA ELC Mathematics 5930 (2017->PRESENT CURRENT)
`

const EDEXCEL = `${COMMON}
BOARD: Edexcel/Pearson. Official PDFs live under https://qualifications.pearson.com/content/dam/pdf/...
Find each spec's landing page on qualifications.pearson.com and the linked specification PDF.
TARGETS:
- Edexcel IGCSE Biology 4BI0 Linear (2009->2016 LEGACY)
- Edexcel IGCSE Biology 4BI1 Linear (2017->PRESENT CURRENT)
- Edexcel IAL Biology WBI01 (2014->2019 LEGACY)
- Edexcel IAL Biology WBI11 (2019->PRESENT CURRENT)
- Edexcel iPrimary Science JSC11 (2018->PRESENT CURRENT)
- Edexcel iLowerSecondary Science LSC11 (2018->PRESENT CURRENT)
- Edexcel ALEVEL Mathematics 8371 (2005->2012 LEGACY)
- Edexcel IGCSE Mathematics 4400 Modular (2005->2012 LEGACY)
- Edexcel IGCSE Mathematics 4MA0 Modular (2011->2016 LEGACY)
- Edexcel IGCSE Mathematics 4MA1 Linear (2016->PRESENT CURRENT)
- Edexcel IAL Mathematics WMA01 (2013->2018 LEGACY)
- Edexcel IAL Mathematics WMA11 (2018->PRESENT CURRENT)
- Edexcel iPrimary Mathematics JMA11 (2018->PRESENT CURRENT)
- Edexcel iLowerSecondary Mathematics LMA11 (2018->PRESENT CURRENT)
`

const OCR = `${COMMON}
BOARD: OCR. Official PDFs live at https://www.ocr.org.uk/Images/<id>-specification-...pdf
Find each spec's subject page on ocr.org.uk and the linked specification PDF.
TARGETS:
- OCR ALEVEL Biology B (Advancing Biology) H422 variant B (2017->PRESENT CURRENT)
- OCR GCSE Biology A (Gateway) J247 variant A (2017->PRESENT CURRENT)  [if the migrated file is Biology B J257, find Biology A J247]
- OCR ALEVEL Mathematics MEI legacy units 4721-4729 (2005->2016 LEGACY)  [or the legacy OCR/MEI Maths specification PDF; Internet Archive ok]
`

const IB = `${COMMON}
BOARD: IB (International Baccalaureate). Guide PDFs live at https://www.ibo.org/globalassets/... or store.ibo.org; older guides via web.archive.org.
TARGETS (Diploma Programme subject guides + MYP/PYP):
- IB DP Biology SL_HL guide, first assessment 2009 (2009->2015 LEGACY)
- IB DP Biology SL_HL guide, first assessment 2016 (2016->2024 LEGACY)
- IB DP Mathematics SL guide, first assessment 2014 (pre-2019 course) (2014->2020 LEGACY)
- IB DP Mathematics HL guide, first assessment 2014 (pre-2019 course) (2014->2020 LEGACY)
- IB DP Mathematics: Applications & Interpretation (AI) SL+HL guide, first assessment 2021 (2021->PRESENT CURRENT)
- IB MYP Mathematics subject guide (2014->PRESENT CURRENT)
- IB PYP Mathematics scope & sequence / framework, 2018 enhanced (2018->PRESENT CURRENT)
- IB PYP Mathematics 2009 framework (2009->2017 LEGACY)
`

phase('Discover')
const [aqa, edx, ocr, ib] = await parallel([
  () => agent(AQA, { label: 'discover:AQA', phase: 'Discover', schema: SCHEMA, agentType: 'Explore' }),
  () => agent(EDEXCEL, { label: 'discover:Edexcel', phase: 'Discover', schema: SCHEMA, agentType: 'Explore' }),
  () => agent(OCR, { label: 'discover:OCR', phase: 'Discover', schema: SCHEMA, agentType: 'Explore' }),
  () => agent(IB, { label: 'discover:IB', phase: 'Discover', schema: SCHEMA, agentType: 'Explore' }),
])

const all = []
for (const r of [aqa, edx, ocr, ib]) {
  if (r && Array.isArray(r.targets)) all.push(...r.targets)
}
log(`discovered ${all.length} candidate targets`)
return { targets: all }
