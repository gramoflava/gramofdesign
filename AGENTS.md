# Agent rules: gramof design

- Site-agnostic. Site names only in: Register, `marks/`, accent blocks, `sites.txt`, provenance line.
- README and `check.py` change together; checkable rules get checked.
- Raw values only in token definitions; new tokens go in README Tokens table.
- After any change: `./check.py --sync`; render every site, light + dark, before committing sites.
- Site exceptions belong in the site (`.gramof.json` + its AGENTS.md). Here only `GLYPH_EXTRA`, with a reason in the Register.
- Products (gramof.us) may borrow; never in `sites.txt`; no product styling here.
- Weights ≤ 600. Fonts: Inter, Outfit, JetBrains Mono (Google link or `fonts/`). Credit third-party assets in THIRD_PARTY_NOTICES.md.
- Docs are for agents: terse, no explanations for humans.
