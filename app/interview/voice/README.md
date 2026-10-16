# Voice interview (ElevenLabs)

The "שיחה קולית" button in `app/interview/index.html` runs the same interview by voice. An
ElevenLabs Conversational AI agent ("Yael", Hebrew voice) listens and speaks; after every patient
answer it calls the `interview_step` client tool, which runs in the page (`voice_flow.js`) against
the rule-based engine. The engine still picks every question and runs the safety screen, so the
LLM only phrases the questions and reads yes/no answers. The clinician tab fills in as the
conversation goes.

Flow: age and sex, pregnancy (women 12-55), red-flag screen, medications, chief complaint, the
engine's screening and adaptive questions, a closing question. A red flag at any point ends the
call with the emergency text from `kb/lexicon/interview_safety.yaml`.

## The agent

Created in the clinic's ElevenLabs workspace (agent `agent_6501m533z4zyfs5brztfqqc7g3gy`, client
tool `tool_9001m533x4nzeydrqjvp586egf24`). `agent_prompt.md` and `first_message.txt` here are the
texts it was configured with; keep them in sync when editing the agent. Settings: language `he`,
voice "Yael" (workspace voice `d4eLZ8u5dfBCsjp4YPyz`), TTS `eleven_v3_conversational`, LLM
`claude-haiku-4-5`, turn eagerness `patient`, built-in `end_call` enabled.

The agent is public (no signed URL), so no API key is in this repo; the page only needs the agent
id in `voice_config.js`. Anyone who has the id can use the clinic's credits, so add an origin
allowlist in the agent's security settings before the page is hosted anywhere public.

## Running it

Open `app/interview/index.html` in Chrome or Edge (or the standalone file built with
`python3 tools/interview/build_interview.py --standalone out.html`), allow the microphone, and
press "שיחה קולית". `?agent=<id>` uses another agent; `?transport=websocket` avoids WebRTC on
networks that block it. The Claude artifact preview cannot use the microphone.
