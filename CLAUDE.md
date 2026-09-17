# Rules for this repo

1. **Test changes before deploying or pushing, with the QA Team AI agent.**
   Before pushing any commit or deploying, verify the change actually works
   — consult/use the dedicated QA Team AI agent to test it. See
   SESSION-NOTES.md in SelfEat-main for which session is currently the QA
   Team. Until that team has covered an area, at minimum boot the app
   against a local SQLite dev DB and smoke-test the changed endpoint(s) with
   curl before pushing. Don't push unverified code.
