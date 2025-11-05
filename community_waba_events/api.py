"""extra community apis to create"""

import operator
from typing import Optional

import frappe
from frappe.model.document import Document
from frappe.utils import cint


@frappe.whitelist(allow_guest=False)
def share_contact():
    """creates a virtual id with context set to share_contact"""
    estate = frappe.form_dict.get("estate")
    if not estate:
        raise frappe.ValidationError("estate required")
    property_unit = frappe.form_dict.get("property_unit")
    if not property_unit:
        raise frappe.ValidationError("property_unit required")

    doc = frappe.get_doc(
        {
            "doctype": "Virtual ID",
            "context": "share_contact",
            "estate": estate,
            "property_unit": property_unit,
        }
    )
    doc.insert()
    return doc


def vcard_esc(text: str) -> str:
    """helper to escape characters per vCard rules"""
    if not text:
        return ""
    return (
        text.replace("\\", "\\\\")
        .replace("\n", " ")
        .replace(";", r"\;")
        .replace(",", r"\,")
    )


def create_social_activity_score(virtual_id, for_virtual_id: Optional[str] = None):
    """indicate that the virtual is has been used"""
    if not for_virtual_id:
        # only award points if code is scanned using scan_contact service
        return None

    docname = virtual_id if isinstance(virtual_id, str) else virtual_id.name
    row = frappe.db.sql(
        """
        SELECT
            p.name, p.community_event, v.owner, v.estate, v.name AS docname, v2.owner AS other
        FROM `tabCommunity Event Participant` AS p
        JOIN `tabVirtual ID` AS v
            ON v.name = %s AND p.community_event = v.estate
        LEFT JOIN `tabVirtual ID` AS v2
            ON v2.name = %s AND v.name != v2.name AND v2.estate = p.community_event
        WHERE p.community_event IS NOT NULL
        AND p.community_user = v.owner
        """,
        (docname, for_virtual_id),
        as_dict=1,
    )
    if not row:
        return None

    row = row[0]
    reference = f"{row.community_event}:{row.owner}:{row.other}"
    if frappe.db.exists("Community Event Activity Score", {"reference": reference}):
        return None
    score = frappe.get_doc(
        {
            "doctype": "Community Event Activity Score",
            "event": row.community_event,
            "participant": row.name,
            "score": 1,
            "reference": reference,
        }
    )
    try:
        score.insert(ignore_permissions=True)
        return score
    except frappe.ValidationError:
        frappe.clear_last_message()
        return None


@frappe.whitelist(allow_guest=True)
def view_contact():
    """downloads contact vcf file for contact with"""

    virtual_id = frappe.form_dict.get("virtual_id")
    if not virtual_id:
        raise frappe.ValidationError("virtual_id required")

    doc = frappe.get_doc("Virtual ID", virtual_id)
    if doc.context != "share_contact":
        raise frappe.ValidationError(
            "contact viewing not permitted for this virtual id"
        )

    user = frappe.get_doc("User", doc.owner)
    first = (user.get("first_name") or "").strip()
    last = (user.get("last_name") or "").strip()
    phone = (user.get("mobile_no") or "").strip() or (user.get("phone") or "").strip()

    if not (first or last or phone):
        raise frappe.ValidationError("No contact information available for linked user")

    score_doc = create_social_activity_score(
        doc, frappe.form_dict.get("for_virtual_id")
    )
    if score_doc:
        frappe.db.commit()

    # Build vCard (VERSION:3.0)
    phone_line = f"TEL;TYPE=CELL:{vcard_esc(phone)}\r\n" if phone else ""
    vcard = (
        "BEGIN:VCARD\r\n"
        "VERSION:3.0\r\n"
        f"N:{vcard_esc(last)};{vcard_esc(first)};;;\r\n"
        f"FN:{vcard_esc((first + ' ' + last).strip())}\r\n"
        f"{phone_line}"
        "END:VCARD\r\n"
    )

    filename = f"{(first or user.name).lower().replace(' ', '_')}.vcf"
    frappe.local.response.filename = filename
    frappe.local.response.filecontent = vcard
    frappe.local.response.type = "download"


def get_top_score(event: str):
    """get the highest score and number of participants"""
    out = frappe.db.sql(
        """
        SELECT
        COALESCE(MAX(t.total_score), 0) AS highest_score,
        COUNT(*) AS participants
        FROM (
        SELECT `participant`, SUM(score) AS total_score
        FROM `tabCommunity Event Activity Score`
        WHERE event = %s
        GROUP BY `participant`
        ) AS t;
    """,
        (event,),
        as_dict=1,
    )
    return out[0] if out else frappe._dict()


def get_participant_score(event: str, participant: str):
    """returns an empty dict if participant has no score yet"""

    out = frappe.db.sql(
        """
        WITH user_totals AS (
        SELECT
            participant,
            SUM(score) AS total_score
        FROM `tabCommunity Event Activity Score`
        WHERE event = %(event)s
        GROUP BY participant
        ),
        ranked AS (
        SELECT
            participant,
            total_score,
            DENSE_RANK() OVER (ORDER BY total_score DESC) AS position,
            CUME_DIST() OVER (ORDER BY total_score) AS cume_dist,
            MAX(total_score) OVER () AS highest_score,
            COUNT(*) OVER () AS participants
        FROM user_totals
        )
        SELECT
        total_score,
        position,
        ROUND(cume_dist * 100, 2) AS percentile,
        highest_score,
        participants
        FROM ranked
        WHERE participant = %(participant)s;
        """,
        {"event": event, "participant": participant},
        as_dict=1,
    )
    return out[0] if out else frappe._dict()


@frappe.whitelist(allow_guest=False)
def leaderboard():
    """community event activity leaderboard"""

    event = frappe.form_dict.get("event")
    if not event:
        raise frappe.ValidationError("event required")

    participant = frappe.db.get_value(
        "Community Event Participant",
        {"community_event": event, "community_user": frappe.session.user},
    )
    if not participant:
        frappe.throw("User is not registered for event")

    score = get_participant_score(event, participant)
    if not score:
        score = {
            "total_score": 0,
            "position": 0,
            "percentile": 0,
            "highest_score": 0,
            "participants": 0,
        }
        score.update(get_top_score(event))

    return score


def current_user_is_event_admin(event: str):
    """ensure current user is an event admin, or Administrator"""
    user = frappe.session.user
    if user == "Administrator":
        return True

    events = frappe.get_all(
        "Community Event",
        fields=["name"],
        filters=[["Community Event Admins", "user", "=", user], ["name", "=", event]],
    )
    return bool(events)


@frappe.whitelist(allow_guest=False)
def get_events():
    """Return events that include current user as admin"""

    events = []
    events_list = frappe.get_all(
        "Community Event",
        fields=["name"],
        filters=[["Community Event Admins", "user", "=", frappe.session.user]],
    )
    for ev in events_list:
        item_count = frappe.db.count("Community Event Items", {"parent": ev.name})
        events.append(
            {
                "name": ev.name,
                "item_count": item_count,
                "route": f"/services/group.html?group={ev.name}",
            }
        )
    return events


@frappe.whitelist(allow_guest=False)
def get_event(event: str):
    """get specific event"""
    if not event:
        frappe.throw("Event name required")

    event = frappe.get_cached_doc("Community Event", event)
    current_user = frappe.session.user
    allowed = any((row.user == current_user) for row in event.get("admins", []))
    if not allowed:
        frappe.throw("You are not an admin for this event")

    return {
        "name": event.name,
        "start": event.start,
        "end": event.end,
        "items": [
            {
                "item": s.item,
                "participant_type": s.participant_type,
                "user_max": s.user_max,
                "event_max": s.event_max,
            }
            for s in event.get("items", [])
        ],
        "admins": [{"user": p.user} for p in event.get("admins", [])],
    }


@frappe.whitelist(allow_guest=False)
def verify_participant(event: str, virtual_id: str):
    """check if a participant is registered for event"""
    if not current_user_is_event_admin(event):
        frappe.throw(f"User is not an admin for event {event=!r}")

    user = frappe.db.get_value("Virtual ID", virtual_id, "owner")
    if not user:
        frappe.throw("Invalid Virtual ID")

    uevent = frappe.db.get_value(
        "Community Event Participant",
        {"community_event": event, "community_user": user},
    )
    if not uevent:
        frappe.throw("User is not registered for event")
    return {"ok": True, "data": frappe.db.get_value("User", user, "full_name")}


@frappe.whitelist(allow_guest=False)
def distribute_item(event: str, item: str, virtual_id: str):
    """indicate that item has been received"""
    if not current_user_is_event_admin(event):
        frappe.throw(f"User is not an admin for event {event=!r}")

    dt = "Community Event Item Receipt"
    user = frappe.db.get_value("Virtual ID", virtual_id, "owner")
    if not user:
        frappe.throw("Invalid Virtual ID")
    p = frappe.db.get_value(
        "Community Event Participant",
        {"community_event": event, "community_user": user},
        fieldname=["name", "participant_type"],
        as_dict=1,
    )
    if not p:
        frappe.throw("User is not registered for event")
    participant = p.name
    ptype = p.participant_type or ""

    # check user max
    for row in frappe.get_cached_doc("Community Event", event).get("items"):
        if row.item == item and ptype == (row.participant_type or ""):
            break
    else:
        frappe.throw(
            f"Invalid Item {item!r} for Event {event!r} and Participant Type {ptype!r}"
        )

    def validate(after=False):
        q = frappe.db.sql(
            f"""SELECT
            COALESCE(SUM(CASE WHEN r.participant = %(participant)s THEN 1 ELSE 0 END), 0) AS user_total,
            COALESCE(SUM(CASE WHEN COALESCE(p.participant_type, "") = %(ptype)s THEN 1 ELSE 0 END), 0) AS event_total
            FROM `tab{dt}` r
            LEFT JOIN `tabCommunity Event Participant` p ON p.name = r.participant
            WHERE r.event = %(event)s
            AND r.item = %(item)s
            """,
            {"event": event, "participant": participant, "ptype": ptype, "item": item},
            as_dict=1,
        )[0]
        op = operator.gt if after else operator.ge
        if cint(row.user_max) >= 0 and op(q.user_total, row.user_max):
            frappe.throw(f"User total ({row.user_max}) exceeded for item {item}")
        if cint(row.event_max) >= 0 and op(q.event_total, row.event_max):
            frappe.throw(f"Event total ({row.event_max}) exceeded for item {item}")

    validate()
    receipt = frappe.get_doc(
        {
            "doctype": dt,
            "event": event,
            "item": item,
            "participant": participant,
            "reference_id": virtual_id,
        }
    )
    receipt.insert(ignore_permissions=True)
    # rerun validations
    # if error occurs, it should rollback
    validate(after=True)
    return receipt


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def get_event_items(doctype, txt, searchfield, start, page_len, filters):

    doctype = "Community Event Item"
    condition = ""
    meta = frappe.get_meta(doctype)
    for fieldname, value in filters.items():
        if meta.get_field(fieldname) or fieldname in frappe.db.DEFAULT_COLUMNS:
            condition += f" and {fieldname}={frappe.db.escape(value)}"

    searchfields = meta.get_search_fields()

    if searchfield and (
        meta.get_field(searchfield) or searchfield in frappe.db.DEFAULT_COLUMNS
    ):
        searchfields.append(searchfield)

    search_condition = ""
    for field in searchfields:
        if search_condition == "":
            search_condition += f"`tab{doctype}`.`{field}` like %(txt)s"
        else:
            search_condition += f" or `tab{doctype}`.`{field}` like %(txt)s"

    return frappe.db.sql(
        """select
			`tabCommunity Event Item`.name
		from
			`tabCommunity Event Item`
		where
			({search_condition})
			{condition}
		limit %(page_len)s offset %(start)s""".format(
            key=searchfield,
            search_condition=search_condition,
            condition=condition or "",
        ),
        {
            "txt": "%" + txt + "%",
            "_txt": txt.replace("%", ""),
            "start": start,
            "page_len": page_len,
        },
    )
