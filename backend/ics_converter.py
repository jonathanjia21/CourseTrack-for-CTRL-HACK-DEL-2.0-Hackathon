"""
Utility to convert extracted assignments JSON to iCalendar (.ics) format.
"""
from datetime import datetime, timedelta
from icalendar import Calendar, Event


def json_to_ics(assignments: list, course_name: str = "Assignments") -> str:
    """
    Convert assignment list to ICS calendar format.
    
    Args:
        assignments: List of dicts with 'title' and 'due_date' (YYYY-MM-DD format)
        course_name: Name of the course/calendar
    
    Returns:
        ICS calendar string
    """
    cal = Calendar()
    cal.add('prodid', '-//Course Track//Assignment Extractor//EN')
    cal.add('version', '2.0')
    cal.add('x-wr-calname', course_name)
    cal.add('x-wr-timezone', 'UTC')
    
    for assignment in assignments:
        if not isinstance(assignment, dict):
            continue
        
        title = assignment.get('title', 'Assignment')
        due_date_str = assignment.get('due_date')
        
        if not due_date_str:
            continue
        
        try:
            # Parse due date (YYYY-MM-DD format)
            due_date = datetime.fromisoformat(due_date_str).date()
            # Shift forward by 1 day to compensate for eClass timezone/display issue
            due_date = due_date + timedelta(days=1)
        except Exception:
            continue
        
        # Create event
        event = Event()
        event.add('summary', title)
        event.add('dtstart', due_date)
        event.add('dtend', due_date)
        event.add('dtstamp', datetime.now())
        event.add('uid', f'{title}-{due_date_str}@coursetrack')
        event.add('description', f'Assignment due: {title}')
        event.add('status', 'CONFIRMED')
        event.add('categories', ['Assignment'])
        
        # All-day event
        event['dtstart'].params['VALUE'] = 'DATE'
        event['dtend'].params['VALUE'] = 'DATE'
        
        cal.add_component(event)
    
    return cal.to_ical().decode('utf-8')


def save_ics_file(assignments: list, filepath: str, course_name: str = "Assignments"):
    """Save assignments as ICS file."""
    ics_content = json_to_ics(assignments, course_name)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(ics_content)
