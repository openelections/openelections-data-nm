import re
import requests
from bs4 import BeautifulSoup
from time import sleep

url_stub = 'https://electionresults.sos.state.nm.us/'
file_name_pattern = '20201103__nm__general__{office}.xlsx'
election_types = ['FED', 'SW', 'RPX', 'SNX']

office_slugs = {
    'President and Vice President of the United States': 'president',
    'United States Representative': 'house__{district}',
    'Secretary of State': 'secretary_of_state',
    'State Representative': 'state_house__{district}',
    'State Senator': 'state_senate__{district}',
}

for election_type in election_types:
    # request the statewide results page
    sw_url_pattern = (
        url_stub +
        'resultsSW.aspx?type={election_type}&map=CTY&lValue=100&gValue=001'
    )
    sw_page_content = requests.get(sw_url_pattern.format(
        election_type=election_type
    ), verify=False).content
    # parse out the table rows
    sw_page_soup = BeautifulSoup(sw_page_content, 'lxml')
    divs = sw_page_soup.find_all('div', class_="display-results-box-wrapper")

    # iterate over table rows
    for div in divs:
        if not div.find('h1'):
            continue
        # parse out the office and district from the race text
        race = div.find('h1').text.split(' - DISTRICT ')
        office = race[0].strip()
        try:
            district = race[1].strip()
        except IndexError:
            district = None
        # find the office slug (if it's defined)
        try:
            office_slug = office_slugs[office].format(district=district)
        except:
            print('   Unknown office: {0}'.format(office))
        if office_slug:
            # continue only if one of the defined offices
            print('   Getting precinct results for {0}...'.format(office))
            # parse out the county results page url
            cty_page_url = url_stub + div.find(
                'span',
                class_='clickfont'
            ).find('a')['href']
            # request the county results page
            cty_page_content = requests.get(cty_page_url, verify=False).content
            cty_page_soup = BeautifulSoup(cty_page_content, 'lxml')
            # parse out the "Export Precinct Level" button url
            export_url = url_stub + cty_page_soup.find(
                'input',
                id='MainContent_rptRace_PrecinctExport_0'
            )['href']
            export_url = export_url.replace('/../', '/')

            with open(
                file_name_pattern.format(office=office_slug),
                'wb'
            ) as f:
                f.write(requests.get(export_url).content)

            sleep(2)

    sleep(2)
