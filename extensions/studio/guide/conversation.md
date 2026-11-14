# How to ask

The design conversation of `speckit.studio.define` and `speckit.studio.map` follows these rules. The person is a product owner: they decide what the product does, and they answer in a few words.

## A round

- Ask in rounds. A round has **at most 10 questions**, and only the questions that are still worth asking: never fill a round to reach 10.
- **One decision per question.** If a question holds an "and", it is two questions.
- Give each question **two to four options**, lettered `a)`, `b)`, `c)`. Mark one as recommended and say why in a few words. An option the person can add in their own words always exists: do not list it.
- Under each question, one line that starts with "It matters because": what changes in the product if they choose otherwise. Leave the line out when the options already say it.
- Put the questions that change the most first: the ones that add or remove a whole area, a kind of person or a rule.
- Number the questions of a round from 1, so the person can answer `1 a, 2 b, 3 recommended, 4 I don't know`.
- Print the whole round as plain text in one message, and wait for the answer. Do not ask the questions one by one, and do not use a question tool that holds fewer questions than the round has.

A round looks like this. Write it in the language the person writes in:

```text
This is what I understood: a neighbourhood app with two kinds of person, one who
signs up for a workshop and one who gives it. To go on I need 4 decisions.

1. Who can publish a workshop?
   a) Any neighbour with an account   (recommended: it is what you wrote)
   b) Only people an administrator approved
   It matters because b) adds an administration area.

2. Is the workshop paid inside the app?   ⚠️ Business decision
   a) No: it is free or paid in person   (recommended for the first version)
   b) Yes, by card
   It matters because b) adds payments, refunds and legal terms.

3. Where will it be used most?
   a) On the phone   (recommended)   b) On the computer   c) The same on both

4. Is there a limit of places per workshop?
   a) Yes, with a waiting list   b) Yes, without a waiting list   c) No limit
```

## What you do around a round

- **Before the first round,** say in three or four lines what you understood from what the person wrote and from the project.
- **After each round,** say in a few lines what is now decided and what changed in your understanding. Then ask the next round, or close.
- **"I don't know" is an answer.** The question stays open with its owner: the person who will decide it. Ask who that is only if it is not the product owner. An open question never stops the rest.
- **A business decision is the person's.** Prices, policies, deadlines, permissions, legal terms and anything that costs or earns money get the mark `⚠️ Business decision`. You may recommend. You never decide one, and you never record one as decided from your own recommendation: only from the person's answer.
- **Bring what is usually forgotten,** when the product can need it: the first use, the account, notices, help, administration, settings, legal terms, languages, accessibility, payments and history. Ask about it, or propose to leave it out and say so.
- **Use the person's words.** If they say "workshop", never call it "event". Keep the words in the glossary of `vision.md`.
- **Ask nothing technical.** Databases, languages, frameworks and servers are decided later, in `plan`.
- **Ask nothing that is already answered** by what the person wrote, by the files of the product or by the project.
- **Before closing, look for contradictions and gaps** in everything decided: a rule that fights another, a screen nobody can reach, a person who has nothing to do, a limit with no number. Put each one to the person as a question.

## Keeping the conversation

Every question lives in `specs/_product/decisions.md`, so the person can stop and go on another day, and nobody asks the same thing twice. The format is in the file guide.

1. **Before you print a round,** write its questions with `- Status: asked`, their `- Options:` and their `- Recommended:`.
2. **When the person answers,** change each one to `- Status: decided` with its `- Answer:`, or to `- Status: open` with its `- Owner:`. Add `- Why:` when the person gave a reason.
3. **When a command starts** and questions are still `asked`, those are the first round: print them again as they are written.

If you cannot ask the person, write the round as `asked`, print it, say that the design waits for those answers, and stop.
