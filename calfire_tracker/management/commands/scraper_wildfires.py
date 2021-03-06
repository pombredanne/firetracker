from django.core.management.base import BaseCommand
from django.utils.encoding import smart_str, smart_unicode
from django.utils.timezone import utc, localtime
from django.core.mail import send_mail, mail_admins, send_mass_mail, EmailMessage
from calfire_tracker.models import CalWildfire
import csv, time, datetime, logging, re, types
from datetime import tzinfo
import pytz
from pytz import timezone
from dateutil import parser
from titlecase import titlecase
from django.conf import settings
from BeautifulSoup import BeautifulSoup, Tag, BeautifulStoneSoup
from scraper_configs import V2Scraper

logging.basicConfig(level=logging.DEBUG)

''' Testing or Live '''
#SCRAPER_STATUS = 'Testing'
SCRAPER_STATUS = 'Live'

class Command(BaseCommand):
    help = 'Scrapes California Wildfires data'
    def handle(self, *args, **options):
        #retrieve_data_from_page()
        open_and_build_list_of_raw_fire_data()
        self.stdout.write('\nScraping finished at %s\n' % str(datetime.datetime.now()))

def open_and_build_list_of_raw_fire_data():
    ''' open local file, convert data table to dictionary & append to list '''

    ''' for local testing from raw html file '''
    if SCRAPER_STATUS == 'Testing':
        target_data = BeautifulSoup(open('incidents_current.html'), convertEntities=BeautifulSoup.HTML_ENTITIES)
    else:
        scraper_instance =V2Scraper()
        raw_html = scraper_instance.retrieve_source_html_with_mechanize('http://cdfdata.fire.ca.gov/incidents/incidents_current?pc=500')
        target_data = BeautifulSoup(raw_html, convertEntities=BeautifulSoup.HTML_ENTITIES)
    ''' for local testing from raw html file '''

    list_of_fires = []
    table_instances = target_data.findAll('table', {'class': 'incident_table'})[1:]
    for table in table_instances:
        individual_fire = {}
        determine_if_details_link_present(table, individual_fire)
        data_points = table.findAll('tr')[1:]
        for row in data_points:
            target_cell = row.findAll('td')
            target_key = lowercase_remove_colon_and_replace_space_with_underscore(target_cell[0].text.encode('utf-8'))
            target_data = target_cell[1].text.encode('utf-8')
            keep_first_instance_of(individual_fire, target_key, target_data)
        individual_fire['created_fire_id'] = '%s-%s' % (individual_fire['name'], individual_fire['county'])

        ###### PAIN POINT ######
        ## round back around to check on last upate ##
        ###### PAIN POINT ######

        list_of_fires.append(individual_fire)
    evaluate_whether_to_follow_details_link(list_of_fires)

def evaluate_whether_to_follow_details_link(list_of_fires):
    ''' lets query the database to compare last_update time stamps '''
    for fire in list_of_fires:
        if fire['details_source'] == 'CalFire' and fire['details_link'] is not None:
            details_scraper =V2Scraper()
            raw_html = details_scraper.retrieve_source_html_with_mechanize(fire['details_link'])
            raw_details = BeautifulSoup(raw_html, convertEntities=BeautifulSoup.HTML_ENTITIES)
            details_table = raw_details.findAll('table', {'class': 'incident_table'})
            for table in details_table:
                determine_if_details_link_present(table, fire)
                data_rows = table.findAll('tr')[1:]
                for row in data_rows:
                    target_cell = row.findAll('td')
                    target_key = lowercase_remove_colon_and_replace_space_with_underscore(target_cell[0].text.encode('utf-8'))
                    target_data = target_cell[1].text.encode('utf-8')
                    keep_first_instance_of(fire, target_key, target_data)
            does_fire_exist_and_is_info_new(fire)
        elif fire['details_source'] == 'CalFire' and fire['details_link'] == None:
            does_fire_exist_and_is_info_new(fire)
        elif fire['details_source'] == 'Riverside County Fire Department':
            does_fire_exist_and_is_info_new(fire)
        elif fire['details_source'] == 'Other':
            does_fire_exist_and_is_info_new(fire)
        elif fire['details_source'] == 'Inciweb':
            inciweb_details_scraper(fire)
        else:
            does_fire_exist_and_is_info_new(fire)

def inciweb_details_scraper(fire):
    ''' pull details from inciweb details page '''

    ''' for local testing from raw html file '''
    if SCRAPER_STATUS == 'Testing':
        target_data = BeautifulSoup(open('inciweb_current.html'), convertEntities=BeautifulSoup.HTML_ENTITIES)
    else:
        details_scraper =V2Scraper()
        raw_html = details_scraper.retrieve_source_html_with_mechanize(fire['details_link'])
        target_data = BeautifulSoup(raw_html, convertEntities=BeautifulSoup.HTML_ENTITIES)
    ''' for local testing from raw html file '''

    ###### PAIN POINT ######
    ## determine how to access text at the top of the inciweb page ##
    ###### PAIN POINT ######

    table_instances = target_data.findAll('table', {'class': 'data'})
    for table in table_instances:
        instance_of_data_rows = {}
        data_rows = table.findAll('tr')[1:]
        for row in data_rows:
            target_key = convert_soup_list_to_data(row.findAll('th'))
            target_key = lowercase_remove_colon_and_replace_space_with_underscore(target_key)
            target_data = convert_soup_list_to_data(row.findAll('td'))
            instance_of_data_rows[target_key] = target_data
        fire.update(instance_of_data_rows)
    construct_inciweb_narrative(fire)

def construct_inciweb_narrative(fire):
    ''' combines narrative paragraphs into one string for later parsing for data points '''
    try:
        acres_burned = fire['size']
        percent_contained = fire['percent_contained']
    except:
        acres_burned = None
        percent_contained = None
    fire['acres_burned_containment'] = '%s -%scontained' % (acres_burned, percent_contained)
    remarks_list = []
    try:
        remarks = '%s' % (fire['remarks'])
        events = '%s' % (fire['significant_events'])
        behavior = '%s' % (fire['fire_behavior'])
        fuel = 'Fuel for the fire includes %s.' % (fire['fuels_involved'])
        terrain = 'Terrain difficulty is %s.' % (fire['terrain_difficulty'])
    except:
        remarks = None
        events = None
        behavior = None
        fuel = None
        terrain = None
    remarks_list.append(remarks)
    remarks_list.append(events)
    remarks_list.append(behavior)
    remarks_list.append(fuel)
    remarks_list.append(terrain)

    try:
        remarks = ' '.join(remarks_list)
        fire['remarks'] = remarks
    except:
        pass
    does_fire_exist_and_is_info_new(fire)

def does_fire_exist_and_is_info_new(fire):
    ''' checks date on newly acquired fire against the database '''
    try:
        query_date_from_database = CalWildfire.objects.get(created_fire_id=fire['created_fire_id'])

        if fire.has_key('last_update'):
            date_comparison_boolean = compare_webpage_to_database(fire['last_update'], query_date_from_database.last_updated)
            fire['update_this_fire'] = date_comparison_boolean
            decide_to_save_or_not(fire)

        elif fire.has_key('last_updated'):
            date_comparison_boolean = compare_webpage_to_database(fire['last_updated'], query_date_from_database.last_updated)
            fire['update_this_fire'] = date_comparison_boolean
            decide_to_save_or_not(fire)

        else:
            fire['update_this_fire'] = True
            save_data_from_dict_to_model(fire)
    except:
        save_data_from_dict_to_model(fire)

def decide_to_save_or_not(fire):
    ''' final determination on whether to save '''

    if fire['update_this_fire'] == True:
        save_data_from_dict_to_model(fire)
    else:
        pass

def save_data_from_dict_to_model(fire):
    ''' save data stored in dict to models '''

    ''' for local testing from raw html file '''
    if SCRAPER_STATUS == 'Testing':
        print fire
    else:
        pass
    ''' for local testing from raw html file '''

    if fire.has_key('name'):
        fire_name = fire['name']
    else:
        fire_name = 'fire_name'

    if fire.has_key('county'):
        county = fire['county']
    else:
        county = None

    if fire.has_key('created_fire_id'):
        created_fire_id = fire['created_fire_id']
    else:
        created_fire_id = '%s-%s' % (fire_name, county)

    twitter_hashtag = '#%s' % (hashtagifyFireName(fire_name))

    if fire.has_key('estimated_containment'):
        acres_burned = extract_acres_integer(fire['estimated_containment'])
        containment_percent = extract_containment_amount(fire['estimated_containment'])
    elif fire.has_key('acres_burned_containment'):
        acres_burned = extract_acres_integer(fire['acres_burned_containment'])
        containment_percent = extract_containment_amount(fire['acres_burned_containment'])
    elif fire.has_key('containment'):
        acres_burned = extract_acres_integer(fire['containment'])
        containment_percent = extract_containment_amount(fire['containment'])
    else:
        acres_burned = None
        containment_percent = 100

    if fire.has_key('details_source'):
        data_source = fire['details_source']
    else:
        data_source = None

    if fire.has_key('date_time_started'):
        date_time_started = convert_time_to_nicey_format(fire['date_time_started'])
        year = date_time_started.year
    elif fire.has_key('date_started'):
        date_time_started = convert_time_to_nicey_format(fire['date_started'])
        year = date_time_started.year
    else:
        date_time_started = None
        year = None

    if fire.has_key('last_updated'):
        last_updated = convert_time_to_nicey_format(fire['last_updated'])
    elif fire.has_key('last_update'):
        last_updated = convert_time_to_nicey_format(fire['last_update'])
    else:
        last_updated = None

    if fire.has_key('administrative_unit'):
        administrative_unit = fire['administrative_unit']
    else:
        administrative_unit = None

    if fire.has_key('details_link'):
        more_info = fire['details_link']
    else:
        more_info = None

    if fire.has_key('location'):
        location = titlecase(fire['location'])
    else:
        location = None

    if fire.has_key('injuries'):
        injuries = extract_initial_integer(fire['injuries'])
    else:
        injuries = None

    if fire.has_key('evacuations'):
        evacuations = fire['evacuations']
    else:
        evacuations = None

    if fire.has_key('structures_threatened'):
        structures_threatened = fire['structures_threatened']
    else:
        structures_threatened = None

    if fire.has_key('structures_destroyed'):
        structures_destroyed = fire['structures_destroyed']
    else:
        structures_destroyed = None

    if fire.has_key('total_dozers'):
        total_dozers = extract_initial_integer(fire['total_dozers'])
    else:
        total_dozers = None

    if fire.has_key('total_helicopters'):
        total_helicopters = extract_initial_integer(fire['total_helicopters'])
    else:
        total_helicopters = None

    if fire.has_key('total_fire_engines'):
        total_fire_engines = extract_initial_integer(fire['total_fire_engines'])
    else:
        total_fire_engines = None

    if fire.has_key('total_fire_personnel'):
        total_fire_personnel = extract_initial_integer(fire['total_fire_personnel'])
    else:
        total_fire_personnel = None

    if fire.has_key('total_water_tenders'):
        total_water_tenders = extract_initial_integer(fire['total_water_tenders'])
    else:
        total_water_tenders = None

    if fire.has_key('total_airtankers'):
        total_airtankers = extract_initial_integer(fire['total_airtankers'])
    else:
        total_airtankers = None

    if fire.has_key('total_fire_crews'):
        total_fire_crews = extract_initial_integer(fire['total_fire_crews'])
    else:
        total_fire_crews = None

    if fire.has_key('cause'):
        cause = fire['cause']
    else:
        cause = None

    if fire.has_key('cooperating_agencies'):
        cooperating_agencies = fire['cooperating_agencies']
    else:
        cooperating_agencies = None

    if fire.has_key('road_closures_'):
        road_closures = fire['road_closures_']
    else:
        road_closures = None

    if fire.has_key('school_closures_'):
        school_closures = fire['school_closures_']
    else:
        school_closures = None

    if fire.has_key('conditions'):
        conditions = fire['conditions']
    else:
        conditions = None

    if fire.has_key('current_situation'):
        current_situation = fire['current_situation']
    elif fire.has_key('remarks'):
        current_situation = fire['remarks']
    else:
        current_situation = None

    if fire.has_key('phone_numbers'):
        phone_numbers = fire['phone_numbers']
    else:
        phone_numbers = None

    last_scraped = datetime.datetime.now()

    county_slug = '%s' % (slugifyFireName(county))

    scraped_fire_slug = '%s' % (slugifyFireName(fire_name))

    if not CalWildfire.objects.filter(fire_slug=scraped_fire_slug).exists():
        fire_slug = scraped_fire_slug
    else:
        fire_slug = '%s-%s' % (scraped_fire_slug, county_slug)

    obj, created = CalWildfire.objects.get_or_create(
        created_fire_id = created_fire_id,

        defaults={
            'twitter_hashtag': twitter_hashtag,
            'last_scraped': last_scraped,
            'data_source': data_source,
            'fire_name': fire_name,
            'county': county,
            'acres_burned': acres_burned,
            'containment_percent': containment_percent,
            'date_time_started': date_time_started,
            'last_updated': last_updated,
            'administrative_unit': administrative_unit,
            'more_info': more_info,
            'fire_slug': fire_slug,
            'county_slug': county_slug,
            'year': year,
            'location': location,
            'injuries': injuries,
            'evacuations': evacuations,
            'structures_threatened': structures_threatened,
            'structures_destroyed': structures_destroyed,
            'total_dozers': total_dozers,
            'total_helicopters': total_helicopters,
            'total_fire_engines': total_fire_engines,
            'total_fire_personnel': total_fire_personnel,
            'total_water_tenders': total_water_tenders,
            'total_airtankers': total_airtankers,
            'total_fire_crews': total_fire_crews,
            'cause': cause,
            'cooperating_agencies': cooperating_agencies,
            'road_closures': road_closures,
            'school_closures': school_closures,
            'conditions': conditions,
            'current_situation': current_situation,
            'phone_numbers': phone_numbers,
        }
    )

    if not created and obj.update_lockout == True:
        pass

    elif created:
        send_new_fire_email(fire_name, acres_burned, county, containment_percent)

    else:
        obj.last_scraped = last_scraped
        obj.acres_burned = acres_burned
        obj.containment_percent = containment_percent
        obj.date_time_started = date_time_started
        obj.last_updated = last_updated
        obj.administrative_unit = administrative_unit
        obj.more_info = more_info
        obj.location = location
        obj.injuries = injuries
        obj.evacuations = evacuations
        obj.structures_threatened = structures_threatened
        obj.structures_destroyed = structures_destroyed
        obj.total_dozers = total_dozers
        obj.total_helicopters = total_helicopters
        obj.total_fire_engines = total_fire_engines
        obj.total_fire_personnel = total_fire_personnel
        obj.total_water_tenders = total_water_tenders
        obj.total_airtankers = total_airtankers
        obj.total_fire_crews =  total_fire_crews
        obj.cause = cause
        obj.cooperating_agencies = cooperating_agencies
        obj.road_closures = road_closures
        obj.school_closures = school_closures
        obj.conditions = conditions
        obj.current_situation = current_situation
        obj.phone_numbers = phone_numbers
        #send_new_fire_email(fire_name, acres_burned, county, containment_percent)
        obj.save()

### begin helper and formatting functions ###
def send_new_fire_email(fire_name, acres_burned, county, containment_percent):
    ''' send email to list when a new fire is added to the database '''
    email_date = datetime.datetime.now().strftime("%A, %b %d, %Y at %I:%M %p")
    email_subject = '%s in %s has been added to Fire Tracker on %s' % (fire_name, county, email_date)
    email_message = '%s has burned %s acres in %s and is at %s%% containment.' % (fire_name, acres_burned, county, containment_percent)
    #mail_admins(email_subject, email_message, fail_silently=True)
    send_mail(email_subject, email_message, 'kpccdatadesk@gmail.com', ['ckeller@scpr.org', 'Ezassenhaus@scpr.org', 'mroe@scpr.org', 'brian.frank@scpr.org',], fail_silently=True)

def lowercase_remove_colon_and_replace_space_with_underscore(string):
    ''' lowercase_remove_colon_and_replace_space_with_underscore '''
    formatted_data = string.lower().replace(':', '').replace(' ', '_').replace('_-_', '_').replace('/', '_')
    return formatted_data

def keep_first_instance_of(target_dict, target_key, target_data):
    ''' keeps first instance of a key and keeps from being overwritten '''
    if target_dict.has_key(target_key):
        pass
    else:
        target_dict[target_key] = target_data

def determine_if_details_link_present(table, individual_fire):
    ''' trying to isolate calfire links when links to other agency on the page '''
    details_links = table.findAll('a')
    if len(details_links) == 0:
        details_source = 'CalFire'
        details_link = None
    elif len(details_links) == 1:
        inciweb_match = re.search('inciweb', details_links[0]['href'])
        riverside_fd_match = re.search('rvcfire.org/_Layouts/Incident', details_links[0]['href'])
        if inciweb_match:
            details_source = 'Inciweb'
            details_link = details_links[0]['href']
        elif riverside_fd_match:
            details_source = 'Riverside County Fire Department'
            details_link = details_links[0]['href']
        else:
            details_source = 'Other'
            details_link = details_links[0]['href']
    else:
        for link in details_links:
            try:
                target_class = link['class']
            except KeyError:
                target_class = ""
            if target_class == 'bluelink':
                details_source = 'CalFire'
                details_link = 'http://cdfdata.fire.ca.gov' + link['href']
            else:
                pass
    individual_fire['details_source'] = details_source
    individual_fire['details_link'] = details_link

def slugifyFireName(string):
    ''' lowercase_and_replace_space_with_dash '''
    formatted_data = string.lower().replace(':', '-').replace(' ', '-').replace('_', '-').replace('_-_', '-').replace('/', '-')
    return formatted_data

def hashtagifyFireName(string):
    ''' lowercase_and_replace_space_with_dash '''
    formatted_data = titlecase(string).replace(' ', '')
    return formatted_data

def convert_time_to_nicey_format(date_time_parse):
    ''' work crazy datetime magic that might be working '''
    ''' based on http://stackoverflow.com/questions/17193228/python-twitter-api-tweet-timestamp-convert-from-utc-to-est '''
    utc = timezone('UTC')
    pacific = pytz.timezone('US/Pacific')
    date_time_parse = parser.parse(date_time_parse)
    pacificizd_date_time_parse = pacific.localize(date_time_parse)
    return pacificizd_date_time_parse

def compare_webpage_to_database(date_from_webpage, date_from_database):
    ''' convert date to datetime, set tzinfo to pacific and compare it as UTC '''
    utc = timezone('UTC')
    pacific = pytz.timezone('US/Pacific')
    parsed_date_from_webpage = parser.parse(date_from_webpage)
    parsed_date_from_webpage = pacific.localize(parsed_date_from_webpage)
    parsed_date_from_webpage = parsed_date_from_webpage.astimezone(utc)
    if date_from_database < parsed_date_from_webpage:
        should_i_update = True
    else:
        should_i_update = False
    return should_i_update

def convert_soup_list_to_data(element):
    ''' takes table row that is a list and converts it to data '''
    for el in element:
        target_data = el.text.encode('utf-8')
        return target_data

def extract_acres_integer(string_to_match):
    ''' runs regex on acres cell to return acres burned as int '''
    #print string_to_match
    number_check = re.compile('\d+\sacres')
    extract_acreage = re.compile('\d+\sacres')
    extract_number = re.compile('^\d+')
    match = re.search(number_check, string_to_match)
    try:
        if match:
            target_number = string_to_match.replace(',', '')
            target_number = re.search(extract_acreage, target_number).group()
            target_number = re.search(extract_number, target_number).group()
            target_number = int(target_number)
        else:
            target_number = None
    except:
        target_number = 'exception'

    #print target_number
    return target_number

def extract_initial_integer(string_to_match):
    ''' runs regex on acres cell to return acres burned as int '''
    print string_to_match
    number_check = re.compile('^\d+')
    extract_number = re.compile('\d+')
    match = re.search(number_check, string_to_match)
    try:
        if match:
            target_number = string_to_match.replace(',', '')
            target_number = re.search(extract_number, target_number)
            target_number = target_number.group()
            target_number = int(target_number)
        else:
            target_number = None
    except:
        target_number = 'exception'

    #print target_number
    return target_number

def extract_containment_amount(string_to_match):
    ''' runs regex on acres cell to return containment as int '''
    extract_number = re.compile('\d+')
    determine_hyphen = re.compile('-')
    percent_match = re.search('%', string_to_match)
    try:
        if percent_match:
            hyphen_match = re.search(determine_hyphen, string_to_match)
            if hyphen_match:
                target_number = re.split('-', string_to_match)
                target_number = re.search(extract_number, target_number[1])
                target_number = target_number.group()
                target_number = int(target_number)
            else:
                target_number = 100
        else:
            target_number = None
    except:
        target_number = 'exception'

    #print target_number
    return target_number

def retrieve_data_from_page():
    ''' save raw html from a web page locally '''
    scraper_instance =V2Scraper()
    raw_html = scraper_instance.retrieve_source_html_with_mechanize('http://cdfdata.fire.ca.gov/incidents/incidents_current?pc=500')
    local_file = scraper_instance.save_source_html_to_file('incidents_current.html', raw_html)