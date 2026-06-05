# TeamOS Discovery: What We Heard
*PM Interviews — Steve Speicher & Garvita Rai | June 2026*
*Conducted by Harekas Bindra, PM Intern*

---

## What We're Building

TeamOS is an internal tool for HashiCorp PMs — a shared brain for product context,
decisions, and cross-team work. We're in the discovery phase, interviewing PMs to
understand where the biggest daily friction lives before writing a line of product code.

---

## Who We Talked To

| Name | Role |
|---|---|
| **Steve Speicher** | PM, Terraform Actions & Ansible Integration |
| **Garvita Rai** | PM, Terraform Core & Core Cloud (apply, plan, CLI) |

---

## What We Heard: Three Themes That Came Up From Both, Unprompted

### 1. Follow-ups are consuming PM time that should go to actual product work

Both Steve and Garvita independently named manual follow-up work as one of their
biggest weekly costs. Garvita, when asked what TeamOS should remove from her week:

> *"All the follow-ups might be nice... it's non-value-add work, whereas you could
> be spending time writing PRDs or doing customer interviews — and instead you're
> pinging people and following up."*

Steve, describing his actual personal reminder system for stalled approvals:

> *"You get pinged, then you wait a week, get pinged again — divide by two at that
> time interval — until they keep getting pinged faster and faster until they do it."*

### 2. Approval stalls are invisible — silence and "blocked" look the same

Sign-offs on PRDs, RFCs, and specs consistently stall. Hermes sends one email when
an approver is added, then nothing. Approvers live in Slack and VS Code, not email.

Garvita: *"I don't think I've seen anyone approve timely without being pushed."*

The deeper problem: there is no way for an approver to communicate status back.
No way to say "I'm reviewing this," "I need a week," or "I'm waiting on X."

Garvita: *"There's no way for people to say 'I'm reviewing this' or 'I'll have time
in a week.' There's a lack of transparency there for sure."*

Steve: after pinging someone multiple times, there is no audit trail — it can look
like the PM never followed up at all.

### 3. PLC process overhead: right intent, wrong execution

Both described PLC as well-intentioned but over-indexed. Neither wants to eliminate
process — they want it scoped to what is actually relevant for their work type.

Garvita: *"They over-indexed on how many things people should do. It's just way too
time consuming."*

Steve: *"It's 100 things to go through, and 80 aren't relevant."*

---

## What We're Working On First

**Automated Approval Tracking & Reminder System**

When a PM creates an approval request linking to a PRD, RFC, or spec, the system:
- Notifies all required approvers via Slack
- Automatically re-notifies on a configurable reminder schedule
- Lets approvers update their status: *reviewing / approved / blocked on X*
- Maintains a full audit trail of every notification and status change
- Surfaces what is pending, who is stalled, and why

This directly removes the most time-consuming non-value-add work both PMs described.

---

## What We Still Need to Learn

- How does Hermes handle approvers today — is there an API or webhook we can connect to?
- Is Slack the right channel for everyone, or do some approvers prefer email?
- Who determines the approver list for a given PRD?
- Do commercial platform PMs share the same approval stall pattern?

---

*Harekas Bindra | PM Intern, TeamOS | IBM HashiCorp*
