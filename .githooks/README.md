# Git hooks

Repo-tracked hooks. Enable them once per clone:

```
git config core.hooksPath .githooks
```

(On the dev box this is set automatically by the initial setup; new clones — including
the Pi — should run the line above.)

- **commit-msg** — strips any AI "co-author"/"generated-with" attribution as a last gate
  before the commit is written. Precise line/link matching, so real content is untouched.
