# ServiceNow setup for Track A (click-by-click)

This covers the ServiceNow-side configuration: the **Catalog Item** (the request form) and the **Flow Designer trigger** (push approach). If you use the **poll** workflow instead, you only need the Catalog Item — skip the Flow Designer section.

> All of this is done inside your free PDI. Log in as `admin`.

## Part 1 — Create the Catalog Item

1. **All** → search `Maintain Items` → **Maintain Items** → **New**.
2. Fill:
   - **Name:** `Request a Virtual Machine`
   - **Catalogue:** `Service Catalog`
   - **Category:** pick any (e.g. `Can We Help You?` or create `Infrastructure`).
   - **Short description:** "Provision a small Linux VM in Azure."
3. **Submit**, then reopen the item to add variables.
4. In the **Variables** related list → **New**, create these (one at a time):

   | Order | Type | Question | Name | Choices |
   |-------|------|----------|------|---------|
   | 100 | Single Line Text | VM name | `vm_name` | — |
   | 200 | Select Box | VM size | `vm_size` | `Standard_B1s`, `Standard_B2s` |
   | 300 | Select Box | OS | `os_type` | `Ubuntu 22.04` |
   | 400 | Select Box | Region | `region` | `centralindia`, `eastus` |

   > For Select Box variables, add **Question Choices** (related list on the variable) for each option.

5. Save. Open **Self-Service → Service Catalog**, find your item, **Order Now**, and confirm a **RITM** appears under `sc_req_item.list`. Note its **Number** (e.g. `RITM0010001`) and **sys_id**.

> 💡 **Test the pipeline manually first** using this RITM number via `workflow_dispatch` before wiring the automatic trigger. Walk before you run.

## Part 2 — (Optional) Approval

Add an approval so provisioning is gated:
- Easiest: in **Flow Designer** (Part 3), add an **Ask for Approval** action before the REST call.
- Or attach an approval workflow to the catalog item. For learning, the Flow Designer approval is simplest.

## Part 3 — Flow Designer trigger (push approach)

### 3a. Create a GitHub PAT
In GitHub: **Settings → Developer settings → Personal access tokens → Tokens (classic) → Generate**, scope **`repo`**. Copy it.

### 3b. Create the Outbound REST Message
1. **All** → `REST Message` → **New**.
   - **Name:** `GitHub Dispatch`
   - **Endpoint:** `https://api.github.com/repos/<owner>/<repo>/dispatches`
2. In the **HTTP Methods** related list → **New**:
   - **Name:** `post-dispatch` · **HTTP method:** `POST` · **Endpoint:** (same as above)
   - **HTTP Headers** (related list):
     - `Authorization` = `Bearer <your-PAT>`
     - `Accept` = `application/vnd.github+json`
     - `Content-Type` = `application/json`
   - **Content** (body) — **recommended: include the variable values directly** (see note):
     ```json
     { "event_type": "provision-vm",
       "client_payload": {
         "number": "${number}", "sys_id": "${sys_id}",
         "vm_name": "${vm_name}", "vm_size": "${vm_size}", "region": "${region}"
       } }
     ```
   - Use **Variable Substitutions** to define each `${...}` (map them in the Flow, Part 3c).

> ### ⭐ Robustness tip — pass variables in the payload, don't query them
> Reading catalog variables back via the Table API (`sc_item_option_mtom` → `sc_item_option`) is **notoriously fiddly on PDIs** — dot-walked fields don't always resolve, and it's the #1 thing that breaks Track A. The **reliable** approach is to send the variable values *in the dispatch payload above*, so the pipeline already has them and only needs the `sys_id` for the write-back.
>
> - **Primary path:** include `vm_name`/`vm_size`/`region` in `client_payload` (as shown). In the workflow, read them from `github.event.client_payload.*` and skip the variable query entirely.
> - **Fallback:** `scripts/fetch_request.py` still queries the variables for the **poll** workflow (where there's no payload). If that query returns nothing, test it in **REST API Explorer** first and adjust the field names to your instance.
3. Click **Test** with a real RITM number to confirm GitHub returns `204 No Content` and the workflow starts.

> 🔐 **Better practice:** store the PAT in a **Credential** record / system property instead of typing it into the header in plain text. For a first pass, plain header is acceptable on your private PDI — but never put it in your Git repo.

### 3c. Build the Flow
1. **All → Flow Designer → New → Flow**. Name: `Provision VM on RITM`.
2. **Trigger:** *Created* → table `Requested Item [sc_req_item]`.
   - Add a **Condition:** `Catalog Item` `is` `Request a Virtual Machine` (and, if using approval, `State` `is` `Approved`/`Work in Progress`).
3. *(Optional)* **Action:** *Ask for Approval* → approver = yourself.
4. **Action:** *Send REST request* (or call the Outbound REST Message via a script step). Map:
   - `number` ← Trigger → Requested Item → Number
   - `sys_id` ← Trigger → Requested Item → Sys ID
5. **Save** → **Activate**.

### 3d. End-to-end test
Order the catalog item again → the flow fires → GitHub Actions runs `provision.yml` → VM created → RITM closes with work notes. Watch the **Actions** tab and the RITM's **Activity** log.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| GitHub returns 401 | Bad/expired PAT | Regenerate PAT with `repo` scope. |
| GitHub returns 422 | Wrong `event_type` | Must match `types: [provision-vm]` in the workflow. |
| Workflow never triggers | Flow not active / wrong condition | Re-check trigger table + condition + Activate. |
| `fetch_request.py` finds no variables | m2m query mismatch on your PDI | Use the manual `workflow_dispatch` first; inspect `sc_item_option_mtom` in REST API Explorer. |
| RITM won't close | State value differs | Confirm the closed-state integer for RITM on your instance (commonly `3`). |

See also [`99-reference/troubleshooting.md`](../../../../99-reference/troubleshooting.md).
