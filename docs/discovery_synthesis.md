# TeamOS Discovery: What We Heard
*17 PM interviews conducted April - June 2026*
*Harekas Bindra, PM Intern | IBM HashiCorp*

---

The same problems came up across 17 interviews with PMs, directors, and field teams.
Different roles, different products, different seniority levels - same friction.
This document summarizes what we found and connects it directly to what this
prototype is built to address.

---

## Who We Talked To

| Name | Role |
|---|---|
| Paul Thrasher | Director of Product Management |
| Sarah Hernandez | PM, Terraform Stacks |
| Marc Cosentino | Group PM, Terraform Integrations |
| Gerald Dagher | PM, Agentic Experiences Platform |
| Jake Lundberg | Field CTO |
| Frederic Lavigne | PM, Terraform Enterprise |
| Richard Rundle | PM, Terraform Enterprise |
| Chris Griggs | PM, Atlas / TFE |
| David Leeper | PM, Visibility Team |
| Garvita Rai | PM, Terraform Core and Core Cloud |
| Steve Speicher | PM, Terraform Actions and Ansible |
| Anya Stettler | PM, Vault Enterprise |
| Roshan Chandna | PM, Agent Experience |
| Vansh Munjal | PM, Terraform Stacks |
| Siteng Yu | PM, Vault Radar and Run Tasks |
| Sharanaa Fathima Safiudeen | PM, Terraform Search |
| V Paul | PM, Terraform Policy |

---

## The Three Problems That Came Up in Every Interview

### 1. Sign-off workflows stall with no audit trail

Hermes sends one notification when an approver is added. After that, silence.
Approvers have no way to signal status back. PMs ping manually, two or three times
per approval, with no record that they did it. Silence and blocked look identical
to the requester. This came up unprompted in 15 of 17 interviews.

The Approval Tracker in this repo is a direct response to this problem. It addresses
the core loop: notify, remind on a schedule, track status per approver, log everything.

### 2. Context is fragmented and never recoverable

Product context lives across Hermes, SharePoint, Google Docs, Slack, email, and
personal spreadsheets simultaneously. No index exists. Discovery happens by accident
or by asking a long-tenured colleague. When people leave - or when an acquisition
happens - institutional knowledge leaves with them.

The IBM acquisition specifically removed Google Docs, the Hermes search experience,
and the IPL field notes email distro with no equivalent replacement for any of them.

Gerald Dagher named the principle that should govern any fix: the difference between
a tool that asks people to add information and one that pulls from where information
already lives. A tool that requires manual input will be abandoned. A tool that reads
from existing sources does not compete for attention.

The Document Store module in this repo is early groundwork toward this layer.

### 3. Customer access is broken and unscalable

Getting to the right customer requires opening a Jira feature request, checking Vivun
for tagged customers, looking up the SE per account in Salesforce, and reaching out
to each one individually on Slack. Multiple PMs described spending hours on this
process for a single research cycle - and still not getting interviews.

Field CTO notes exist but are effectively undiscoverable since moving from an email
distro to a W3 blog format. Cross-PM customer notes disappeared with the IPL field
notes system and have not been replaced.

The GitHub Signal Pipeline in this repo addresses one slice of this: surfacing OSS
customer signal from public GitHub issues without manual outreach.

---

## What This Prototype Covers

| Problem | Module | Status |
|---|---|---|
| Sign-off workflows stall | Approval Tracker | Functional |
| OSS signal requires manual outreach | GitHub Signal Pipeline | Functional |
| PM knowledge artifacts unorganized | Document Store | In progress |

---

## What Is Not Yet Built

- Hermes integration for the Approval Tracker
- Jira and Salesforce connectors for the SE outreach loop
- LLM summarization on top of the signal pipeline clusters
- A shared dashboard view across approvals and signals
- The full context recovery layer Gerald described

---

*Harekas Bindra | PM Intern, Team OS Working Group | IBM HashiCorp*
