# Project Report Outline

Use this file as the submission scaffold for the Group 1 report.

## 1. Project Title

- DIU Assistant
- Group 1: DIU admission, program, scholarship, and document-grounded assistant

## 2. Problem Statement

- explain the need for a DIU-focused assistant
- describe the confusion students face around admissions, programs, waivers, and official documents

## 3. Objectives

- provide grounded DIU question answering
- support uploaded-document understanding
- support specialist-style academic/admission guidance
- keep the deployed system aligned with localhost behavior

## 4. System Architecture

- summarize the frontend
- summarize the Python backend
- explain the DIU site index and uploaded-document pipeline
- include the architecture diagram from `docs/architecture.md`

## 5. Methodology

- DIU site indexing and retrieval
- Gemini grounding and prompting
- document parsing and uploaded context memory
- production deployment architecture

## 6. Features Implemented

- general DIU assistant
- admission/program/scholarship guidance
- uploaded-document RAG flow
- canvas/artifact generation
- observability and failure logging

## 7. Testing And Evaluation

- backend tests
- frontend tests
- smoke questions used for manual verification
- known limitations and edge cases

## 8. Deployment

- localhost architecture
- published architecture
- why `static frontend + permanent Python backend` is the final design

## 9. Challenges And Fixes

- keeping production behavior aligned with localhost
- retrieval relevance/noise handling
- streamed-response issues in production proxying

## 10. Future Work

- retrieval quality improvements
- always-on backend hosting
- richer monitoring and evaluation sets
- more accurate deadline/date grounding
