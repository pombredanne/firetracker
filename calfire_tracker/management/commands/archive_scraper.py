###### TO DOS ######

# determine fire['details_source']
# inciweb_details_scraper()
# determine how to access text at the top of the inciweb page
# construct_inciweb_narrative()
# does_fire_exist_and_is_info_new()
# decide_to_save_or_not()
# send_new_fire_email()
# determine_if_details_link_present()
# extract_acres_integer()
# extract_containment_amount()

from django.core.management.base import BaseCommand
from django.utils.encoding import smart_str, smart_unicode
from django.utils.timezone import utc, localtime
from django.core.mail import send_mail, mail_admins, send_mass_mail, EmailMessage
from calfire_tracker.models import CalWildfire
from django.conf import settings
import sys, csv, time, datetime, logging, re, types, pytz, requests, glob
from datetime import tzinfo
from pytz import timezone
from dateutil import parser
from titlecase import titlecase
from bs4 import BeautifulSoup
from atm import ATM

logging.basicConfig(level=logging.DEBUG)

# requests headers
REQUESTS_HEADERS = {
    "From": "ckeller@scpr.org",
    "User-Agent": "Mozilla/5.0 (Windows; U; Windows NT 6.0; en-US) AppleWebKit/525.19 (KHTML, like Gecko) Chrome/1.0.154.53 Safari/525.19"
}

# 2011 fires
TARGET_URL = "http://cdfdata.fire.ca.gov/incidents/incidents_archived?archive_year=2011&pc=500"
TARGET_FILE = "/Users/ckeller/Desktop/fire_cache/archived_fires_2011.html"

class Command(BaseCommand):
    help = "scrapes wildfire data from CalFire for a given URL"
    def handle(self, *args, **options):
        #cache_local_html(TARGET_URL)
        create_soup_from_local_html(TARGET_FILE)
        self.stdout.write("\nScraping finished at %s\n" % str(datetime.datetime.now()))

class type_wildfire():
    def __init__(self, fires_without_link, fires_with_single_link, fires_with_multiple_links, fires_with_edge_cases):
        self.fires_without_link = fires_without_link
        self.fires_with_single_link = fires_with_single_link
        self.fires_with_multiple_links = fires_with_multiple_links
        self.fires_with_edge_cases = fires_with_edge_cases

class single_wildfire():
    def __init__(self, created_fire_id, twitter_hashtag, last_scraped, data_source, fire_name, county, acres_burned, containment_percent, date_time_started, last_updated, administrative_unit, more_info, fire_slug, county_slug, year, location, injuries, evacuations, structures_threatened, structures_destroyed, total_dozers, total_helicopters, total_fire_engines, total_fire_personnel, total_water_tenders, total_airtankers, total_fire_crews, cause, cooperating_agencies, road_closures, school_closures, conditions, current_situation, phone_numbers):
        self.created_fire_id = created_fire_id
        self.twitter_hashtag = twitter_hashtag
        self.last_scraped = last_scraped
        self.data_source = data_source
        self.fire_name = fire_name
        self.county = county
        self.acres_burned = acres_burned
        self.containment_percent = containment_percent
        self.date_time_started = date_time_started
        self.last_updated = last_updated
        self.administrative_unit = administrative_unit
        self.more_info = more_info
        self.fire_slug = fire_slug
        self.county_slug = county_slug
        self.year = year
        self.location = location
        self.injuries = injuries
        self.evacuations = evacuations
        self.structures_threatened = structures_threatened
        self.structures_destroyed = structures_destroyed
        self.total_dozers = total_dozers
        self.total_helicopters = total_helicopters
        self.total_fire_engines = total_fire_engines
        self.total_fire_personnel = total_fire_personnel
        self.total_water_tenders = total_water_tenders
        self.total_airtankers = total_airtankers
        self.total_fire_crews = total_fire_crews
        self.cause = cause
        self.cooperating_agencies = cooperating_agencies
        self.road_closures = road_closures
        self.school_closures = school_closures
        self.conditions = conditions
        self.current_situation = current_situation
        self.phone_numbers = phone_numbers

def cache_local_html(target_url):
    teller = ATM("/Users/ckeller/Desktop/fire_cache', format='txt")
    r = teller.get_cache(target_url)
    r.is_s3 = False

def create_soup_from_local_html(target_file):
    '''
        open local html file
    '''
    soup_html = BeautifulSoup(open(target_file))
    find_tables_of_fires(soup_html)

def find_tables_of_fires(html):
    '''
        for 2011 we're working with 124 tables
        find the tables container fire instances
    '''
    fire_table_instances = html.find_all("table", {"class": "incident_table"})[1:]
    assign_fires_to_type_class(fire_table_instances)

def assign_fires_to_type_class(list_of_fires):
    fires_without_link = []
    fires_with_single_link = []
    fires_with_multiple_links = []
    fires_with_edge_cases = []
    for fire in list_of_fires:
        try:
            link_to_detail = fire.find_all("a")
            if len(link_to_detail) == 0:
                fires_without_link.append(fire)
            elif len(link_to_detail) == 1:
                fires_with_single_link.append(fire)
            elif len(link_to_detail) == 2:
                fires_with_multiple_links.append(fire)
            else:
                fires_with_edge_cases.append(fire)
        except (KeyError, TypeError, ValueError):
                logging.debug("Unexpected error:", sys.exc_info()[0])
    logging.debug("fires_without_link: %d" % (len(fires_without_link)))
    logging.debug("fires_with_single_link: %d" % (len(fires_with_single_link)))
    logging.debug("fires_with_multiple_links: %d" % (len(fires_with_multiple_links)))
    logging.debug("fires_with_edge_cases: %d" % (len(fires_with_edge_cases)))
    this_type_of_wildfire = type_wildfire(fires_without_link, fires_with_single_link, fires_with_multiple_links, fires_with_edge_cases)
    process_fires_without_link(this_type_of_wildfire.fires_without_link)

def process_fires_without_link(fires_without_link):
    for fire in fires_without_link:
        fire_dict = {}
        data_rows = fire.find_all('tr')[1:]
        for row in data_rows:
            data_points = row.find_all('td')
            try:
                date_key = data_points[0].text.encode('utf-8').rstrip('\n')
                data_key = string_manipulation.manipulate_string(date_key, 'lowercase', 'remove_colon', 'replace_space_with_underscore', 'replace_slash_with_underscore')
                data_value = data_points[1].text.encode('utf-8')
                if fire_dict.has_key(data_key):
                    pass
                else:
                    fire_dict[data_key] = data_value.rstrip('\xc2\xa0').rstrip('\xe2\x80\xac')
            except (KeyError, TypeError, ValueError):
                    logging.debug("Unexpected error:", sys.exc_info()[0])
        create_instance_of_fire_class_from(fire_dict)

def create_instance_of_fire_class_from(fire):

    logging.debug(fire)

    if fire.has_key('name'):
        fire_name = fire['name']
        fire_slug = string_manipulation.manipulate_string(fire_name, 'slugify')
    else:
        fire_name = 'fire_name'
        fire_slug = 'fire_name_none'
    logging.debug(fire_name)
    logging.debug(fire_slug)

    if fire.has_key('county'):
        county = fire['county']
        county_slug = string_manipulation.manipulate_string(county, 'slugify')
    else:
        county = None
        county_slug = None
    logging.debug(county)
    logging.debug(county_slug)

    created_fire_id = '%s-%s' % (fire_name, county)
    logging.debug(created_fire_id)

    twitter_hashtag = '#%s' % (string_manipulation.manipulate_string(fire_name, 'hashtagify'))
    logging.debug(twitter_hashtag)

    acres_burned = None
    containment_percent = None

    '''
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
    '''







    if fire.has_key('details_source'):
        data_source = fire['details_source']
    else:
        data_source = None
    logging.debug(data_source)

    if fire.has_key('date_time_started'):
        date_time_started = data_formatting.ensure_datetime_timezone(fire['date_time_started'])
        year = date_time_started.year
    elif fire.has_key('date_started'):
        date_time_started = data_formatting.ensure_datetime_timezone(fire['date_started'])
        year = date_time_started.year
    else:
        date_time_started = None
        year = None
    logging.debug(date_time_started)
    logging.debug(year)

    if fire.has_key('last_updated'):
        last_updated = data_formatting.ensure_datetime_timezone(fire['last_updated'])
    elif fire.has_key('last_update'):
        last_updated = data_formatting.ensure_datetime_timezone(fire['last_update'])
    else:
        last_updated = None
    logging.debug(last_updated)

    if fire.has_key('administrative_unit'):
        administrative_unit = fire['administrative_unit']
    else:
        administrative_unit = None
    logging.debug(administrative_unit)

    if fire.has_key('details_link'):
        more_info = fire['details_link']
    else:
        more_info = None
    logging.debug(more_info)

    if fire.has_key('location'):
        location = titlecase(fire['location'])
    else:
        location = None
    logging.debug(location)

    if fire.has_key('injuries'):
        injuries = data_formatting.extract_initial_integer(fire['injuries'])
    else:
        injuries = None
    logging.debug(injuries)

    if fire.has_key('evacuations'):
        evacuations = fire['evacuations']
    else:
        evacuations = None
    logging.debug(evacuations)

    if fire.has_key('structures_threatened'):
        structures_threatened = fire['structures_threatened']
    else:
        structures_threatened = None
    logging.debug(structures_threatened)

    if fire.has_key('structures_destroyed'):
        structures_destroyed = fire['structures_destroyed']
    else:
        structures_destroyed = None
    logging.debug(structures_destroyed)

    if fire.has_key('total_dozers'):
        total_dozers = data_formatting.extract_initial_integer(fire['total_dozers'])
    else:
        total_dozers = None
    logging.debug(total_dozers)

    if fire.has_key('total_helicopters'):
        total_helicopters = data_formatting.extract_initial_integer(fire['total_helicopters'])
    else:
        total_helicopters = None
    logging.debug(total_helicopters)

    if fire.has_key('total_fire_engines'):
        total_fire_engines = data_formatting.extract_initial_integer(fire['total_fire_engines'])
    else:
        total_fire_engines = None
    logging.debug(total_fire_engines)

    if fire.has_key('total_fire_personnel'):
        total_fire_personnel = data_formatting.extract_initial_integer(fire['total_fire_personnel'])
    else:
        total_fire_personnel = None
    logging.debug(total_fire_personnel)

    if fire.has_key('total_water_tenders'):
        total_water_tenders = data_formatting.extract_initial_integer(fire['total_water_tenders'])
    else:
        total_water_tenders = None
    logging.debug(total_water_tenders)

    if fire.has_key('total_airtankers'):
        total_airtankers = data_formatting.extract_initial_integer(fire['total_airtankers'])
    else:
        total_airtankers = None
    logging.debug(total_airtankers)

    if fire.has_key('total_fire_crews'):
        total_fire_crews = data_formatting.extract_initial_integer(fire['total_fire_crews'])
    else:
        total_fire_crews = None
    logging.debug(total_fire_crews)

    if fire.has_key('cause'):
        cause = fire['cause']
    else:
        cause = None
    logging.debug(cause)

    if fire.has_key('cooperating_agencies'):
        cooperating_agencies = fire['cooperating_agencies']
    else:
        cooperating_agencies = None
    logging.debug(cooperating_agencies)

    if fire.has_key('road_closures_'):
        road_closures = fire['road_closures_']
    else:
        road_closures = None
    logging.debug(road_closures)

    if fire.has_key('school_closures_'):
        school_closures = fire['school_closures_']
    else:
        school_closures = None
    logging.debug(school_closures)

    if fire.has_key('conditions'):
        conditions = fire['conditions']
    else:
        conditions = None
    logging.debug(conditions)

    if fire.has_key('current_situation'):
        current_situation = fire['current_situation']
    elif fire.has_key('remarks'):
        current_situation = fire['remarks']
    else:
        current_situation = None
    logging.debug(current_situation)

    if fire.has_key('phone_numbers'):
        phone_numbers = fire['phone_numbers']
    else:
        phone_numbers = None
    logging.debug(phone_numbers)

    last_scraped = pytz.timezone('US/Pacific').localize(datetime.datetime.now())
    last_scraped = last_scraped.astimezone(utc)
    logging.debug(last_scraped.tzinfo)

    this_wildfire = single_wildfire(created_fire_id, twitter_hashtag, last_scraped, data_source, fire_name, county, acres_burned, containment_percent, date_time_started, last_updated, administrative_unit, more_info, fire_slug, county_slug, year, location, injuries, evacuations, structures_threatened, structures_destroyed, total_dozers, total_helicopters, total_fire_engines, total_fire_personnel, total_water_tenders, total_airtankers, total_fire_crews, cause, cooperating_agencies, road_closures, school_closures, conditions, current_situation, phone_numbers)

    logging.debug(this_wildfire)
    save_wildfire_to_model(this_wildfire)

def save_wildfire_to_model(this_wildfire):
    logging.debug(this_wildfire)

    ''' save data from class instance to database models '''
    obj, created = CalWildfire.objects.get_or_create(
        created_fire_id = this_wildfire.created_fire_id,

        defaults={
            'twitter_hashtag': this_wildfire.twitter_hashtag,
            'last_scraped': this_wildfire.last_scraped,
            'data_source': this_wildfire.data_source,
            'fire_name': this_wildfire.fire_name,
            'county': this_wildfire.county,
            'acres_burned': this_wildfire.acres_burned,
            'containment_percent': this_wildfire.containment_percent,
            'date_time_started': this_wildfire.date_time_started,
            'last_updated': this_wildfire.last_updated,
            'administrative_unit': this_wildfire.administrative_unit,
            'more_info': this_wildfire.more_info,
            'fire_slug': this_wildfire.fire_slug,
            'county_slug': this_wildfire.county_slug,
            'year': this_wildfire.year,
            'location': this_wildfire.location,
            'injuries': this_wildfire.injuries,
            'evacuations': this_wildfire.evacuations,
            'structures_threatened': this_wildfire.structures_threatened,
            'structures_destroyed': this_wildfire.structures_destroyed,
            'total_dozers': this_wildfire.total_dozers,
            'total_helicopters': this_wildfire.total_helicopters,
            'total_fire_engines': this_wildfire.total_fire_engines,
            'total_fire_personnel': this_wildfire.total_fire_personnel,
            'total_water_tenders': this_wildfire.total_water_tenders,
            'total_airtankers': this_wildfire.total_airtankers,
            'total_fire_crews': this_wildfire.total_fire_crews,
            'cause': this_wildfire.cause,
            'cooperating_agencies': this_wildfire.cooperating_agencies,
            'road_closures': this_wildfire.road_closures,
            'school_closures': this_wildfire.school_closures,
            'conditions': this_wildfire.conditions,
            'current_situation': this_wildfire.current_situation,
            'phone_numbers': this_wildfire.phone_numbers,
        }
    )

    if not created and obj.update_lockout == True:
        pass

    #elif created:
        #send_new_fire_email(fire_name, acres_burned, county, containment_percent)

    else:
        obj.last_scraped = this_wildfire.last_scraped
        obj.data_source = this_wildfire.data_source
        obj.acres_burned = this_wildfire.acres_burned
        obj.containment_percent = this_wildfire.containment_percent
        obj.date_time_started = this_wildfire.date_time_started
        obj.last_updated = this_wildfire.last_updated
        obj.administrative_unit = this_wildfire.administrative_unit
        obj.more_info = this_wildfire.more_info
        obj.location = this_wildfire.location
        obj.injuries = this_wildfire.injuries
        obj.evacuations = this_wildfire.evacuations
        obj.structures_threatened = this_wildfire.structures_threatened
        obj.structures_destroyed = this_wildfire.structures_destroyed
        obj.total_dozers = this_wildfire.total_dozers
        obj.total_helicopters = this_wildfire.total_helicopters
        obj.total_fire_engines = this_wildfire.total_fire_engines
        obj.total_fire_personnel = this_wildfire.total_fire_personnel
        obj.total_water_tenders = this_wildfire.total_water_tenders
        obj.total_airtankers = this_wildfire.total_airtankers
        obj.total_fire_crews =  this_wildfire.total_fire_crews
        obj.cause = this_wildfire.cause
        obj.cooperating_agencies = this_wildfire.cooperating_agencies
        obj.road_closures = this_wildfire.road_closures
        obj.school_closures = this_wildfire.school_closures
        obj.conditions = this_wildfire.conditions
        obj.current_situation = this_wildfire.current_situation
        obj.phone_numbers = this_wildfire.phone_numbers
        #send_new_fire_email(fire_name, acres_burned, county, containment_percent)
        obj.save()

class string_manipulation():
    ''' format the strings '''
    @staticmethod
    def manipulate_string(string, *args):
        '''
            accepts a string and arguments that determines
            how the string should be manipulated and returned
        '''
        for arg in args:
            if arg == 'lowercase':
                string = string_manipulation.lowercase(string)
            if arg == 'remove_colon':
                string = string_manipulation.remove_colon(string)
            if arg == 'replace_space_with_underscore':
                string = string_manipulation.replace_space_with_underscore(string)
            if arg == 'replace_dash_with_underscore':
                string = string_manipulation.replace_dash_with_underscore(string)
            if arg == 'replace_slash_with_underscore':
                string = string_manipulation.replace_slash_with_underscore(string)
            if arg =='slugify':
                string = string_manipulation.slugify(string)
            if arg =='hashtagify':
                string = string_manipulation.hashtagify(string)
        return string

    @staticmethod
    def lowercase(string):
        ''' lowercase string '''
        formatted = string.lower()
        return formatted

    @staticmethod
    def remove_colon(string):
        ''' remove colon from string '''
        formatted = string.replace(':', '')
        return formatted

    @staticmethod
    def replace_space_with_underscore(string):
        ''' replace space in string with underscore '''
        formatted = string.replace(' ', '_')
        return formatted

    @staticmethod
    def replace_dash_with_underscore(string):
        ''' replace dash in string with underscore '''
        formatted = string.replace('-', '_')
        return formatted

    @staticmethod
    def replace_slash_with_underscore(string):
        ''' replace dash in string with underscore '''
        formatted = string.replace('/', '_')
        return formatted

    @staticmethod
    def slugify(string):
        ''' slugify_fire_name '''
        formatted = string.lower().replace(':', '-').replace(' ', '-').replace('_', '-').replace('_-_', '-').replace('/', '-')
        return formatted

    @staticmethod
    def hashtagify(string):
        ''' hashtagify_fire_name '''
        formatted = titlecase(string).replace(' ', '')
        return formatted

class data_formatting():
    ''' format data points '''
    @staticmethod
    def ensure_datetime_timezone(date_time):
        '''
            work crazy datetime magic that might be working
            http://stackoverflow.com/questions/17193228/python-twitter-api-tweet-timestamp-convert-from-utc-to-est
        '''
        utc = timezone('UTC')
        pacific = pytz.timezone('US/Pacific')
        date_time = parser.parse(date_time)
        if date_time.tzinfo is None:
            pacific_datetime = pacific.localize(date_time)
            utc_datetime = pacific_datetime.astimezone(utc)
            return utc_datetime
        else:
            logging.debug(date_time.tzinfo)
            return date_time

    @staticmethod
    def extract_initial_integer(string):
        '''
            runs regex on acres cell to return acres burned as int
        '''
        number_check = re.compile('^\d+')
        extract_number = re.compile('\d+')
        match = re.search(number_check, string)
        try:
            if match:
                target_number = string.replace(',', '')
                target_number = re.search(extract_number, target_number)
                target_number = target_number.group()
                target_number = int(target_number)
            else:
                target_number = None
        except (KeyError, TypeError, ValueError):
            logging.debug("Unexpected error:", sys.exc_info()[0])
            target_number = 'exception'
        return target_number