from flask import Flask, request, jsonify, render_template, redirect, url_for, flash
from collections import OrderedDict
import uuid
from datetime import datetime, timedelta, timezone
import threading
import time

app = Flask(__name__)

# Global variable to store the active scenario and last event
active_scenario = None
last_event = None
last_doc_incarnation = 1
app.secret_key = 'test_key'

# Predefined scenarios
# Dev timing scenarios have all their timings in seconds 
# So instead of waiting 15 minutes for an event to appear, it'll take 15 seconds
# to prevent waiting when testing locally.
# The other scenarios have the timings convert the times to minutes to match what
# would happen in production 
scenarios = {
    "Live Migration - Dev Timing": {
        "EventId": str(uuid.uuid4()),
        "NotBeforeDelayInMinutes": 15,
        "StartedDurationInMinutes": 5,
        "EventStatus": OrderedDict([
            ("Scheduled", 15),
            ("Started", 5),
            ("Completed", 0)
        ]),
        "EventType": "Freeze",
        "Description": "Virtual machine is being paused because of a memory-preserving Live Migration operation.",
        "ScenarioDescription": """This scenario simulates a live migration. LMs 
            can be triggered by the platform in the case of host maintenance or if 
            there is a predicted host failure.""",
        "EventSource": "Platform",
        "DurationInSeconds": 5,
    },
    "User Reboot - Dev Timing": {
        "EventId": str(uuid.uuid4()),
        "NotBeforeDelayInMinutes": 15,
        "StartedDurationInMinutes": 10,
        "EventStatus": OrderedDict([
            ("Scheduled", 15),
            ("Started", 10),
            ("Completed", 0)
        ]),
        "EventType": "Reboot",
        "Description": "Virtual machine is going to be restarted as requested by authorized user.",
        "ScenarioDescription": """This scenario simulates a reboot initiated by 
            the user. This can be triggered via the portal or CLI if you'd like 
            to test with a real reboot""",
        "EventSource": "User",
        "DurationInSeconds": -1,
    },
    "Host Agent Maintenance - Dev Timing": {
        "EventId": str(uuid.uuid4()),
        "NotBeforeDelayInMinutes": 15,
        "StartedDurationInMinutes": 10,
        "EventStatus": OrderedDict([
            ("Scheduled", 15),
            ("Started", 10),
            ("Completed", 0)
        ]),
        "EventType": "Freeze",
        "Description": "Host server is undergoing maintenance.",
        "ScenarioDescription": """This scenario simulates host maintenance, which 
            is the most common reason for a scheduled event. The VM is typically frozen for 
            between 1 and 15 seconds, but the time between the started and completed 
            events is longer to allow Azure to run health checks after the maintenance.""",
        "EventSource": "Platform",
        "DurationInSeconds": 9,
    },
    "Redeploy - Dev Timing": {
        "EventId": str(uuid.uuid4()),
        "NotBeforeDelayInMinutes": 15,
        "StartedDurationInMinutes": 10,
        "EventStatus": OrderedDict([
            ("Scheduled", 15),
            ("Started", 10),
            ("Completed", 0)
        ]),
        "EventType": "Redeploy",
        "Description": "Virtual machine has encountered a failure.",
        "ScenarioDescription": """This scenario simulates a platform-initiated redeploy "
            due to a host failure.""",
        "EventSource": "Platform",
        "DurationInSeconds": -1
    },
    "User Redeploy - Dev Timing": {
        "EventId": str(uuid.uuid4()),
        "NotBeforeDelayInMinutes": 15,
        "StartedDurationInMinutes": 10,
        "EventStatus": OrderedDict([
            ("Scheduled", 15),
            ("Started", 10),
            ("Completed", 0)
        ]),
        "EventType": "Redeploy",
        "Description": "Virtual machine is going to be redeployed as requested by authorized user.",
        "ScenarioDescription": """This scenario simulates a redeploy initiated by 
            the user. This event can also be triggered via the portal or CLI""",
        "EventSource": "User",
        "DurationInSeconds": -1
    },
    "Canceled Maintenance - Dev Timing": {
        "EventId": str(uuid.uuid4()),
        "NotBeforeDelayInMinutes": 15,
        "StartedDurationInMinutes": 10,
        "EventStatus": OrderedDict([
            ("Scheduled", 8),
            ("Canceled", 0)
        ]),
        "EventType": "Freeze",
        "Description": "Host server is undergoing maintenance.",
        "ScenarioDescription": """This scenario simulates the rare case where a 
            maintenance event that was canceled. This can happen if Azure detects other 
            hosts receiving the same maintenance event are failing health checks. The 
            system will cancel any pending maintenance events and pause the maintenance until
            a root cause can be determined.""",
        "EventSource": "Platform",
        "DurationInSeconds": 9,
    },
    "Live Migration": {
        "EventId": str(uuid.uuid4()),
        "NotBeforeDelayInMinutes": 15,
        "StartedDurationInMinutes": 5,
        "EventStatus": OrderedDict([
            ("Scheduled", 15 * 60),
            ("Started", 5 * 60),
            ("Completed", 0)
        ]),
        "EventType": "Freeze",
        "Description": "Virtual machine is being paused because of a memory-preserving Live Migration operation.",
        "ScenarioDescription": """This scenario simulates a live migration. LMs 
            can be triggered by the platform in the case of host maintenance or if 
            there is a predicted host failure.""",
        "EventSource": "Platform",
        "DurationInSeconds": 5,
    },
    "User Reboot": {
        "EventId": str(uuid.uuid4()),
        "NotBeforeDelayInMinutes": 15,
        "StartedDurationInMinutes": 10,
        "EventStatus": OrderedDict([
            ("Scheduled", 15 * 60),
            ("Started", 10 * 60),
            ("Completed", 0)
        ]),
        "EventType": "Reboot",
        "Description": "Virtual machine is going to be restarted as requested by authorized user.",
        "ScenarioDescription": """This scenario simulates a reboot initiated by 
            the user. This can be triggered via the portal or CLI if you'd like 
            to test with a real reboot""",
        "EventSource": "User",
        "DurationInSeconds": -1,
    },
    "Host Agent Maintenance": {
        "EventId": str(uuid.uuid4()),
        "NotBeforeDelayInMinutes": 15,
        "StartedDurationInMinutes": 10,
        "EventStatus": OrderedDict([
            ("Scheduled", 15 * 60),
            ("Started", 10 * 60),
            ("Completed", 0)
        ]),
        "EventType": "Freeze",
        "Description": "Host server is undergoing maintenance.",
        "ScenarioDescription": """This scenario simulates host maintenance, which 
            is the most common reason for a scheduled event. The VM is typically frozen for 
            between 1 and 15 seconds, but the time between the started and completed 
            events is longer to allow Azure to run health checks after the maintenance.""",
        "EventSource": "Platform",
        "DurationInSeconds": 9,
    },
    "Redeploy": {
        "EventId": str(uuid.uuid4()),
        "NotBeforeDelayInMinutes": 15,
        "StartedDurationInMinutes": 10,
        "EventStatus": OrderedDict([
            ("Scheduled", 15 * 60),
            ("Started", 10 * 60),
            ("Completed", 0)
        ]),
        "EventType": "Redeploy",
        "Description": "Virtual machine has encountered a failure.",
        "ScenarioDescription": """This scenario simulates a platform-initiated redeploy "
            due to a host failure.""",
        "EventSource": "Platform",
        "DurationInSeconds": -1
    },
    "User Redeploy": {
        "EventId": str(uuid.uuid4()),
        "NotBeforeDelayInMinutes": 15,
        "StartedDurationInMinutes": 10,
        "EventStatus": OrderedDict([
            ("Scheduled", 15 * 60),
            ("Started", 10 * 60),
            ("Completed", 0)
        ]),
        "EventType": "Redeploy",
        "Description": "Virtual machine is going to be redeployed as requested by authorized user.",
        "ScenarioDescription": """This scenario simulates a redeploy initiated by 
            the user. This event can also be triggered via the portal or CLI""",
        "EventSource": "User",
        "DurationInSeconds": -1
    },
    "Canceled Maintenance": {
        "EventId": str(uuid.uuid4()),
        "NotBeforeDelayInMinutes": 15,
        "StartedDurationInMinutes": 10,
        "EventStatus": OrderedDict([
            ("Scheduled", 8 * 60),
            ("Canceled", 0)
        ]),
        "EventType": "Freeze",
        "Description": "Host server is undergoing maintenance.",
        "ScenarioDescription": """This scenario simulates the rare case where a 
            maintenance event that was canceled. This can happen if Azure detects other 
            hosts receiving the same maintenance event are failing health checks. The 
            system will cancel any pending maintenance events and pause the maintenance until
            a root cause can be determined.""",
        "EventSource": "Platform",
        "DurationInSeconds": 9,
    },
    # Add scenario for Spot VM Eviction
    "Spot Eviction": {
        "EventId": str(uuid.uuid4()),
        "NotBeforeDelayInMinutes": 15,
        "StartedDurationInMinutes": 5,
        "EventStatus": OrderedDict([
            ("Scheduled", 15),
            ("Started", 5),
            ("Completed", 0)
        ]),
        "EventType": "Preempt",
        "Description": "The Virtual Machine will be evicted.",
        "ScenarioDescription": """This scenario simulates eviction of a Spot Virtual Machine.
            The Spot Virtual Machine is being deleted (ephemeral disks are lost). This event is made available on a best effort basis""",
        "EventSource": "Platform",
        "DurationInSeconds": -1,
    }
    # Add more scenarios as needed
}

@app.route('/', methods=['GET', 'POST'])
def index():
    """
    Render the main page with the scenario and event status selection form.
    Allow user to set the resources array.
    """
    global resources_list
    # Handle resource input from the form
    if request.method == 'POST':
        resources_input = request.form.get('resources', 'vmss_vm1')
        # Split by comma and strip whitespace
        resources_list = [r.strip() for r in resources_input.split(',') if r.strip()]
    else:
        resources_list = ['vmss_vm1']

    # Prepare IMDS event format for the last event, if it exists
    imds_event = None
    if last_event:
        scenario_details = last_event["ActiveScenario"]
        event_status = last_event["EventStatus"]
        if event_status in scenario_details["EventStatus"] and event_status in ["Completed", "Canceled"]:
            imds_event = {
                "DocumentIncarnation": last_doc_incarnation,
                "Events": []
            }
        else:
            if event_status == "Scheduled":
                offset = scenario_details.get("NotBeforeDelayInMinutes", 0)
                not_before_time = (datetime.utcnow() + timedelta(minutes=offset)).strftime("%Y-%m-%dT%H:%M:%SZ")
            else:
                not_before_time = ""
            imds_event = {
                "DocumentIncarnation": last_doc_incarnation,
                "Events": [
                    {
                        "EventId": last_event["EventId"],
                        "EventStatus": event_status,
                        "EventType": scenario_details["EventType"],
                        "ResourceType": "VirtualMachine",
                        "Resources": resources_list if resources_list else ["vmss_vm1"],
                        "EventSource": scenario_details["EventSource"],
                        "NotBefore": not_before_time,
                        "Description": scenario_details["Description"],
                        "DurationInSeconds": scenario_details["DurationInSeconds"]
                    }
                ]
            }
    return render_template(
        'index.html',
        scenarios=scenarios,
        active_scenario=active_scenario,
        last_event=last_event,
        last_doc_incarnation=last_doc_incarnation,
        imds_event=imds_event,
        resources=','.join(resources_list) if 'resources_list' in globals() else 'vmss_vm1'
    )

@app.route('/set-scenario', methods=['POST'])
def set_scenario():
    """
    Set the active scenario based on user selection from the web UI.
    Also resets last_event so NotBefore is recalculated for the new scenario.
    """
    global active_scenario, last_event
    scenario_name = request.form.get("scenario")
    if scenario_name not in scenarios:
        return redirect(url_for('index'))

    active_scenario = scenario_name
    last_event = None  # Reset event state so NotBefore is recalculated
    return redirect(url_for('index'))

@app.route('/generate-event', methods=['POST'])
def generate_event():
    """
    Generate a mock event based on the active scenario and user-selected event status.
    """
    global last_event, last_doc_incarnation, active_scenario, resources_list
    if not active_scenario:
        flash("No active scenario. Please set a scenario first.", "error")
        return redirect(url_for('index'))

    event_status = request.form.get("event_status")
    if event_status not in scenarios[active_scenario]["EventStatus"]:
        flash("Invalid event status selected.", "error")
        return redirect(url_for('index'))

    # Get resources from form or use default
    resources_input = request.form.get('resources', 'vmss_vm1')
    resources_list = [r.strip() for r in resources_input.split(',') if r.strip()]

    # Set NotBefore time for the event
    scenario = scenarios[active_scenario]
    not_before_time = None
    if event_status == "Scheduled":
        offset = scenario.get("NotBeforeDelayInMinutes", 0)
        not_before_time = (datetime.now(timezone.utc) + timedelta(minutes=offset)).strftime("%Y-%m-%dT%H:%M:%SZ")

    event_id = str(uuid.uuid4())
    event = {
        "EventId": event_id,
        "Scenario": active_scenario,
        "EventStatus": event_status,
        "ActiveScenario": scenario,
        "NotBefore": not_before_time,
        "Resources": resources_list if resources_list else ["vmss_vm1"]
    }
    last_event = event
    last_doc_incarnation += 1
    flash(f"New event generated", "success")
    return redirect(url_for('index'))

@app.route('/metadata/scheduledevents', methods=['GET', 'POST'])
def imds_scheduledevents():
    """
    Respond as if this is the IMDS scheduled events endpoint.
    GET: Returns the last generated event in IMDS format.
    POST: Handles StartRequests to advance event state if EventId matches and status is Scheduled.
    """
    global last_event, last_doc_incarnation, stop_auto_run, auto_run_thread

    # Handle POST for StartRequests
    if request.method == 'POST':
        if not last_event:
            return jsonify({
                "DocumentIncarnation": last_doc_incarnation,
                "Events": []
            }), 400

        try:
            data = request.get_json(force=True)
        except Exception:
            return jsonify({"error": "Invalid JSON"}), 400

        start_requests = data.get("StartRequests", [])
        if start_requests and isinstance(start_requests, list):
            event_id_in_request = start_requests[0].get("EventId")
            # Check if eventId matches and current event is Scheduled
            if (
                event_id_in_request == last_event.get("EventId")
                and last_event.get("EventStatus") == "Scheduled"
            ):
                scenario = last_event["ActiveScenario"]
                event_statuses = list(scenario["EventStatus"].keys())
                try:
                    idx = event_statuses.index("Scheduled")
                    # Move to next status if possible
                    if idx + 1 < len(event_statuses):
                        next_status = event_statuses[idx + 1]
                        # Keep NotBefore unchanged
                        event_id = str(uuid.uuid4())
                        event = {
                            "EventId": event_id,
                            "Scenario": last_event["Scenario"],
                            "EventStatus": next_status,
                            "ActiveScenario": scenario,
                            "NotBefore": last_event.get("NotBefore"),
                            "Resources": last_event.get("Resources", ["vmss_vm1"])
                        }
                        last_event = event
                        last_doc_incarnation += 1
                        # Do NOT stop auto-run; let playback continue
                        # (Remove or comment out: stop_auto_run.set())
                except ValueError:
                    pass  # "Scheduled" not found, do nothing

        # Return the current event after processing
        event = last_event
        scenario_details = event["ActiveScenario"]
        event_status = event["EventStatus"]
        not_before_time = event.get("NotBefore")
        resources = event.get("Resources", ["vmss_vm1"])

        # If the event is Completed or Canceled, return an empty Events list
        if event_status in scenario_details["EventStatus"] and event_status in ["Completed", "Canceled"]:
            return jsonify({
                "DocumentIncarnation": last_doc_incarnation,
                "Events": []
            }), 200

        # If status is Started, NotBefore must be an empty string
        if event_status == "Started":
            not_before_time = ""

        imds_event = {
            "EventId": event["EventId"],
            "EventStatus": event_status,
            "EventType": scenario_details["EventType"],
            "ResourceType": "VirtualMachine",
            "Resources": resources,
            "EventSource": scenario_details["EventSource"],
            "NotBefore": not_before_time if not_before_time else "",
            "Description": scenario_details["Description"],
            "DurationInSeconds": scenario_details["DurationInSeconds"]
        }
        return jsonify({
            "DocumentIncarnation": last_doc_incarnation,
            "Events": [imds_event]
        }), 200

    # Existing GET logic below...
    if not last_event:
        return jsonify({
            "DocumentIncarnation": last_doc_incarnation,
            "Events": []
        }), 200

    event = last_event
    scenario_details = event["ActiveScenario"]
    event_status = event["EventStatus"]
    not_before_time = event.get("NotBefore")
    resources = event.get("Resources", ["vmss_vm1"])

    if event_status in scenario_details["EventStatus"] and event_status in ["Completed", "Canceled"]:
        return jsonify({
            "DocumentIncarnation": last_doc_incarnation,
            "Events": []
        }), 200

    if event_status == "Started":
        not_before_time = ""

    imds_event = {
        "EventId": event["EventId"],
        "EventStatus": event_status,
        "EventType": scenario_details["EventType"],
        "ResourceType": "VirtualMachine",
        "Resources": resources,
        "EventSource": scenario_details["EventSource"],
        "NotBefore": not_before_time if not_before_time else "",
        "Description": scenario_details["Description"],
        "DurationInSeconds": scenario_details["DurationInSeconds"]
    }
    return jsonify({
        "DocumentIncarnation": last_doc_incarnation,
        "Events": [imds_event]
    }), 200

auto_run_thread = None
stop_auto_run = threading.Event()

def auto_run_scenario():
    global last_event, last_doc_incarnation, active_scenario, stop_auto_run
    scenario = scenarios[active_scenario]
    event_statuses = list(scenario["EventStatus"].keys())
    durations = list(scenario["EventStatus"].values())
    not_before_time = None
    idx = 0
    while idx < len(event_statuses):
        status = event_statuses[idx]
        if stop_auto_run.is_set() or (last_event is not None and active_scenario != last_event.get("Scenario", None)):
            break
        # Only set NotBefore for the first event if not already set
        if idx == 0:
            if last_event is None or last_event.get("NotBefore") is None:
                if status == "Scheduled":
                    offset = scenario.get("NotBeforeDelayInMinutes", 0)
                    not_before_time = (datetime.now(timezone.utc) + timedelta(minutes=offset)).strftime("%Y-%m-%dT%H:%M:%SZ")
                else:
                    not_before_time = None
            else:
                not_before_time = last_event.get("NotBefore") if last_event is not None else None
        else:
            not_before_time = last_event.get("NotBefore") if last_event is not None else None
        event_id = str(uuid.uuid4())
        event = {
            "EventId": event_id,
            "Scenario": active_scenario,
            "EventStatus": status,
            "ActiveScenario": scenario,
            "NotBefore": not_before_time
        }
        last_event = event
        last_doc_incarnation += 1

        # Wait for the duration of the current state, but if the user POSTs to advance the state,
        # the idx will be incremented externally and the sleep will be for the next state's duration.
        sleep_time = durations[idx] if idx < len(durations) else 0
        # Sleep in small increments to allow interruption by POST
        slept = 0
        while slept < sleep_time:
            if stop_auto_run.is_set():
                break
            time.sleep(1)
            slept += 1
            # If the event has advanced (e.g., via POST), break early and continue with the new state
            if last_event["EventStatus"] != status:
                # Find the new index based on the updated status
                try:
                    idx = event_statuses.index(last_event["EventStatus"])
                except ValueError:
                    idx += 1  # fallback: just move to next
                break
        else:
            idx += 1  # Only increment if not interrupted by POST

    # After reaching the last state, keep returning the same event until user changes scenario

@app.route('/auto-run-scenario', methods=['POST'])
def auto_run_scenario_route():
    global active_scenario, auto_run_thread, stop_auto_run
    if not active_scenario:
        flash("No active scenario. Please set a scenario first.", "error")
        return redirect(url_for('index'))
    stop_auto_run.set()  # Stop any previous auto-run
    stop_auto_run = threading.Event()  # Reset event
    def run():
        auto_run_scenario()
    auto_run_thread = threading.Thread(target=run, daemon=True)
    auto_run_thread.start()
    flash("Automatically running scenario.", "success")
    return redirect(url_for('index'))

@app.route('/stop-auto-run', methods=['POST'])
def stop_auto_run_route():
    global stop_auto_run, last_event
    stop_auto_run.set()
    stop_auto_run = threading.Event()
    last_event = None
    flash("Event playback stopped and reset.", "success")
    return redirect(url_for('index'))

if __name__ == '__main__':
    # Start the Flask web server
    app.run(host='127.0.0.1', port=80, debug=False)


