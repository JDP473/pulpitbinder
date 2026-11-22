# Usability walk-throughs

A way to watch someone use Pulpit Binder for the first time without recruiting anyone: a smaller Claude model plays a
preacher who has never seen the app, drives a real browser one step at a time, sees only screenshots, and reports where
it got lost. Smaller models are used on purpose. They do not fill gaps with cleverness, so when one of them cannot tell
what a button does, a tired preacher on a Saturday night probably cannot either.

It finds labels nobody understands, buttons with no name, things cut off or covered on a phone, and steps that do
something the user did not expect. It does not replace a real person: a model reads every word on the screen, never
squints, and is patient in ways people are not. Treat what it reports as leads, and look at the screenshot it names
before changing anything.

## Running one

Start a browser for each tester (each needs its own port and folder):

```bash
python3 tests/usability/serve.py 9711 desktop light /tmp/ut/a first   # a new preacher: only the example sermon
python3 tests/usability/serve.py 9712 phone light /tmp/ut/b           # 26 generic sermons already saved
```

Then give a model the brief below, with its port. In Claude Code that is an agent on the `haiku` or `sonnet` model. The
tester uses only `tests/usability/do` and reads the screenshots it names:

```bash
tests/usability/do 9711 look                      # screenshot
tests/usability/do 9711 click 120 300             # click or tap a point
tests/usability/do 9711 type "The Good Shepherd"  # type into whatever has focus
tests/usability/do 9711 key Enter                 # press a key
tests/usability/do 9711 scroll 400                # scroll down (negative for up)
tests/usability/do 9711 choose 530 486 "Sunday PM"   # pick from a dropdown at that point
tests/usability/do 9711 select-text "exact words" # highlight words on the page
tests/usability/do 9711 upload 1070 272 tests/fixtures/deck.pptx
tests/usability/do 9711 controls                  # the buttons and fields on screen, with coordinates
```

Every step lands in `OUTDIR/log.jsonl` with its screenshot, so the path a tester took can be read back.

Claude's features are answered by `mock.js`, a stand-in with short generic answers and placeholder verse wording. No
Bible text and no sermon content belongs in it.

## The brief

Keep these parts, and change the person and the tasks:

> You are taking part in a usability test of a web app called Pulpit Binder. Play this person: (who they are, how
> comfortable with computers, whether they have seen the app). You are (at a desktop, or holding a phone).
>
> You may ONLY use these commands and the Read tool on the screenshots they produce. Do not read any source code or
> other files: a real user cannot, and it would spoil the test. (List the commands with the port.)
>
> The app's Claude features are answered by a canned stand-in, so generic AI content is not a finding, but how the app
> shows waiting, results, and errors is.
>
> Think aloud. Before each click, say in one line what you expect to happen; after it, say whether that happened. If a
> task is not done after about 10 actions, stop it, mark it FAILED, and move on. Do not be polite.
>
> TASKS, in order: (five to nine things a preacher would actually do, in his words, never naming the button)
>
> REPORT: for each task, done or failed, the number of actions, wrong turns, and the moment of confusion with the
> screenshot that shows it. Then the problems, most serious first, with where, what happened, why it would trip a real
> preacher, and a one-line fix. Then what worked well. Only report what you saw, and say when a problem might be the
> test tool and not the app.

Write tasks as goals ("find out how long this sermon will take to preach"), not as directions ("open Analysis").
Run several testers at once on different tasks, on a desktop and on a phone, and at least one in dark mode.

## Reading the results

- Count a problem when two testers hit it, or when one hit it and the screenshot plainly shows it.
- Check for test-setup causes first. The seeded sermons carry a made-up analysis date, saving goes to a silent stub, and
  the stand-in answers in under a second, so "no spinner" and "nothing happened when I saved" are often not real.
- What gets fixed gets a check in `tests/browser/usability.py`, so it stays fixed.
