# Approval Tracker: Demo Script
*For showing Paul Thrasher or Sarah Hernandez before Tuesday*

---

## The one-sentence setup

15 of 17 PMs we interviewed named stalled sign-off workflows as a top pain point.
Hermes sends one notification and then nothing. PMs ping manually with no record it
happened. This tool closes that loop.

---

## What to say before you type anything

"Every PM I talked to described the same thing: you publish a document in Hermes,
you get silence, you start pinging people manually, and there is no record of any
of it. If a deadline slips, it looks like you never followed up even if you did it
five times. This is a working prototype that replaces that whole loop."

---

## Step 1: Show the dashboard

```bash
python src/approval_tracker.py dashboard
```

What you will see: the Team OS PRFAQ request, open, with @sarah and @gerald as
approvers, grouped by urgency. Point out:
- The request is real - it was created for the actual PRFAQ
- You can see at a glance who is pending, reviewing, or blocked
- No more opening Hermes to figure out what is waiting on whom

---

## Step 2: Show reminders without sending anything

```bash
python src/reminder_runner.py --dry-run
```

What you will see: which approvers would be notified right now and why.
Point out:
- This runs automatically on a cron job every weekday morning
- The PM does not have to remember to follow up - the system does it
- Every reminder is logged to the audit trail

---

## Step 3: Show an approver updating their status

```bash
python src/approval_tracker.py update \
  --id <first 8 chars of the request id from dashboard output> \
  --approver @sarah \
  --status reviewing
```

Then run dashboard again:

```bash
python src/approval_tracker.py dashboard
```

What you will see: @sarah now shows the reviewing icon instead of pending.
Point out:
- This is the thing that does not exist in Hermes today
- Silence and blocked look identical in the current process
- Now an approver can say exactly where they are without a Slack message

---

## Step 4: Show a blocked approver with a note

```bash
python src/approval_tracker.py update \
  --id <request id prefix> \
  --approver @gerald \
  --status blocked \
  --note "Waiting on security review first"
```

Run dashboard again. Point out:
- The note is visible immediately in the dashboard
- The requester knows exactly why it is blocked without chasing anyone
- This is logged to the audit trail permanently

---

## Step 5: Show the audit trail

```bash
python src/approval_tracker.py audit --id <request id prefix>
```

What you will see: every event since the request was created - created, reminders
sent, status changes, with timestamps.

Point out:
- This is the record that does not exist today
- If a deadline slips and someone asks why, this is the answer
- Every notification count is tracked per approver

---

## If they ask what is missing

Be direct. Three things are not built yet:
1. Hermes integration - right now this runs from the command line, not inside Hermes
2. A shared team dashboard - right now it reads from a local JSON file
3. Approver notification via actual Slack - the webhook works but needs a real workspace URL

All three are the next steps. The core loop - create, notify, remind, track status,
audit - is fully functional right now.

---

## If Paul says he does not want another tool to go to

He said this in his interview. His concern is adoption. Acknowledge it directly:

"You said in the interview that tools fail when they require behavior change. That
is exactly right. The long-term version of this is integrated into Hermes so the
PM never has to go somewhere new. This prototype proves the loop works before we
build the integration. The question is whether the loop is the right one."

---

## If Sarah asks about the knowledge base problem

That is Problem 2 in the discovery synthesis. This prototype addresses Problem 1.
Tell her:

"This is the fastest win from the interviews. Problem 2 - context fragmentation -
is the foundational one and it is what the Team OS repo is built for. This is the
piece that can be piloted right now without waiting for infrastructure."

---

*Harekas Bindra | PM Intern | IBM HashiCorp*
