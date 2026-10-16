// The ElevenLabs agent that speaks the interview (see voice/README.md for how it is set up).
// An agent id is not a secret, but this agent is public: anyone holding the id can start a
// conversation on the clinic's ElevenLabs credits. Restrict it with an origin allowlist before
// sharing the page outside the clinic. Override per page load with ?agent=<id>.
window.TCM_VOICE_CONFIG = {
  agentId: "agent_6501m533z4zyfs5brztfqqc7g3gy"
};
