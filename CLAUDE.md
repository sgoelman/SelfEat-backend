# Rules for this repo

1. **Test before pushing.** Before pushing any commit, verify the change
   actually works — run the test suite once one exists for the changed area;
   until then, at minimum boot the app against a local SQLite dev DB and
   smoke-test the changed endpoint(s) with curl before pushing. Don't push
   unverified code.
