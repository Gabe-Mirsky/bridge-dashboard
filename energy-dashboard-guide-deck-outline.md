# Energy Dashboard Guide Deck Outline

## Deck Goal

This presentation is a hand-holding guide for coworkers who do not code but may need to update, republish, or maintain the Bridge Energy dashboard website after I leave the office.

The tone should be practical, calm, and step-by-step. Every slide should answer:

- What is this?
- Why would I touch it?
- What exactly do I click or change?
- How do I know I did it correctly?

## Recommended Deck Title

Energy Dashboard Guide  
How To Update, Publish, and Maintain the Website Without Coding Experience

---

## Slide 1: Title Slide

### Title
Energy Dashboard Guide

### Subtitle
How to update, republish, and safely maintain the Bridge dashboard

### Speaker Notes
This deck is meant to be both a training walkthrough and a reference guide. If you forget something later, you should be able to come back to this deck and follow the steps.

---

## Slide 2: Why This Exists

### Title
Why This Guide Exists

### Bullets
- The dashboard is business-critical and should not depend on one person.
- Most future updates should not require coding knowledge.
- AI can help with edits, but there is still a safe process to follow.
- This guide shows what to change, how to publish, and how to avoid breaking the website.

### Speaker Notes
Set expectations: they do not need to become developers. They do need to follow a repeatable process carefully.

---

## Slide 3: What The Dashboard Is Made Of

### Title
What Makes Up the Website

### Simple Breakdown
- `index.html`: the structure of the page
- `style.css`: the visual styling and spacing
- `script.js`: the behavior, layout logic, and rotating content
- `server.py`: the backend that serves data and powers the site

### Plain-English Translation
- HTML = what appears on the page
- CSS = how it looks
- JavaScript = how it moves/updates
- Python server = how data gets pulled and displayed

### Speaker Notes
Keep this simple. The goal is not to teach web development. The goal is to help them know where a future change probably lives.

---

## Slide 4: Where To Go To Access The Code

### Title
Where To Access The Code

### Bullets
- Open the project folder: `bridge-dashboard`
- Main working files are:
- `index.html`
- `style.css`
- `script.js`
- `server.py`

### Add Callout
If the request is about spacing, colors, text size, icons, or layout, start with `style.css` or `script.js`.

### Speaker Notes
This is the “doc to get into code” slide from the notes. Make this very visual and simple.

---

## Slide 5: What Types Of Changes Are Easy

### Title
Common Changes You Can Make

### Two-Column Layout

#### Left Column: Usually Easy
- Update visible wording
- Change spacing
- Change colors
- Change font sizes
- Reorder rotating sections
- Swap icons
- Resize images

#### Right Column: More Care Needed
- Changing live market data logic
- Editing weather/backend APIs
- Changing deploy behavior
- Reworking multiple sections at once

### Speaker Notes
The point is to reduce fear while still warning them where mistakes are more likely.

---

## Slide 6: The Safest Workflow For Any Change

### Title
Safest Workflow For Future Changes

### Numbered Steps
1. Decide exactly what should change.
2. Identify which file likely controls that part.
3. Make one small change at a time.
4. Refresh the local site and verify visually.
5. Commit changes with a clear message.
6. Republish the website.
7. Confirm the live site looks correct.

### Speaker Notes
This is one of the most important slides. It gives them a repeatable process.

---

## Slide 7: How AI Can Help

### Title
How To Use AI Without Knowing How To Code

### Bullets
- Describe the change in plain English.
- Be specific about where it is on the page.
- Ask AI to change only one area at a time.
- Always verify the result visually before publishing.
- If something breaks, ask AI to explain what changed before asking for another fix.

### Example Prompts
- “In Q4, make the NOAA images larger without changing the rest.”
- “Move the Hartford icon above the summary.”
- “Reduce the gap between the stock name and price in Q2.”

### Speaker Notes
Emphasize that AI works best when requests are specific and narrow.

---

## Slide 8: How Someone Can Make Changes Without Coding Knowledge

### Title
How To Make Changes Without Knowing How To Code

### Bullets
- Use AI as a translator between plain English and code.
- Start by describing:
- where the change is
- what it should look like
- what should not change
- Review the updated site visually after every request.
- Never stack many unrelated edits into one request.

### Speaker Notes
This directly addresses the “how someone else could make change without knowing how to code” note.

---

## Slide 9: How To Republish The Website

### Title
How To Republish The Website

### Numbered Steps
1. Save the updated files.
2. Stage changes with Git.
3. Commit with a message.
4. Push to the main branch.
5. Wait for the deploy process to complete.
6. Refresh the live site and confirm the change.

### Command Block
```powershell
git add .
git commit -m "Describe the change"
git push
```

### Speaker Notes
This is the “how to republish the website” slide. Keep it operational, not technical.

---

## Slide 10: What To Do If Git Does Not Work

### Title
If Git Gives An Error

### Bullets
- If `git` is not recognized, the terminal may need the Git path loaded.
- Close and reopen PowerShell if needed.
- If Git still fails, use the full Git executable path.
- Do not guess; use the exact commands in this guide.

### Add Small Reference Box
Known Git path on this machine:
`C:\Users\GabeMirsky-BridgeEne\AppData\Local\Programs\Git\cmd\git.exe`

### Speaker Notes
This came up repeatedly and is worth preserving.

---

## Slide 11: How To Know If A Change Worked

### Title
How To Verify A Change Worked

### Checklist
- The targeted section looks correct.
- Nothing else visually broke.
- Text is not cut off.
- Data still loads correctly.
- The live site matches the intended result.
- If backend code changed, the app/server was restarted if needed.

### Speaker Notes
Verification needs its own slide so they do not stop after making the edit.

---

## Slide 12: White Page Troubleshooting

### Title
If The Website Shows A White Page

### Bullets
- This usually means something broke in `script.js`, `index.html`, or `server.py`.
- Undo the most recent risky change first.
- Check whether the server is running.
- Check whether the browser console or terminal shows an error.
- If needed, ask AI: “The site is a white page. Help me find the most likely broken file.”

### Speaker Notes
This directly addresses the “White page” note from your rough list.

---

## Slide 13: Which File To Check First

### Title
Which File Should I Check First?

### Table
- Layout issue -> `style.css`
- Text issue -> `index.html` or `script.js`
- Rotation/order issue -> `script.js`
- Missing live data -> `script.js` and `server.py`
- Publish/deploy issue -> Git process or deploy workflow
- Whole page broken -> `script.js`, `index.html`, or `server.py`

### Speaker Notes
This is the fast reference slide they will probably use the most later.

---

## Slide 14: Good Requests To Give AI

### Title
Examples Of Good AI Requests

### Good Examples
- “In Q2, reduce the space between the stock name and the price.”
- “In Hartford Extended, show the full summary instead of truncating it.”
- “Make the Chicago icon appear between temperature and description.”
- “Do not change any other quadrant.”

### Bad Examples
- “Fix the website.”
- “Make it better.”
- “Update everything.”

### Speaker Notes
This helps them get usable results faster.

---

## Slide 15: Rules To Avoid Breaking The Site

### Title
Rules To Follow Every Time

### Bullets
- Change one area at a time.
- Verify before pushing.
- Use clear commit messages.
- Do not publish if something else on the page looks broken.
- If a backend file changed, remember the server may need a restart.
- When unsure, stop and ask for help before stacking more edits.

### Speaker Notes
This is the “future maintenance without chaos” slide.

---

## Slide 16: Final Quick Reference

### Title
Quick Reference

### Short Version
- Find the right file
- Make one small change
- Refresh and verify
- Commit
- Push
- Confirm the live site

### Closing Line
You do not need to know how to code. You do need to follow the process.

---

## Optional Appendix Slides

### Appendix A: Common File Map
- Q2 market snapshot -> `script.js` and `style.css`
- Q3 oil/fuels board -> `script.js` and `style.css`
- Q4 weather/news -> `script.js`, `style.css`, and sometimes `server.py`

### Appendix B: Common Commands
```powershell
git status
git add .
git commit -m "message"
git push
```

### Appendix C: When To Restart The App
- Any `server.py` change
- Any backend data-source logic update
- Any change that affects how the page is served

## Recommended Visual Style For The Deck

- Use your “Energy Dashboard Guide” template as the base.
- Keep the deck visually simple and reassuring.
- Use screenshots of the dashboard where helpful.
- Use one slide to show the file structure visually.
- Use one slide to show the publish workflow visually.
- Use callout boxes for “If this breaks, check here first.”

## Suggested Order For Delivery

1. Explain the dashboard at a high level.
2. Show where the files live.
3. Show the safe change workflow.
4. Show how AI can help.
5. Show how to republish.
6. Show how to troubleshoot white-page failures.
7. End with the quick-reference slide.
