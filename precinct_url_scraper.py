import re
import requests
from bs4 import BeautifulSoup
from time import sleep

url_stub = 'http://electionresults.sos.state.nm.us/'
file_name_pattern = '20141104__nm__general__{office}.xlsx'
election_types = ['FED', 'SW', 'LGX']

office_slugs = {
    'Governor and Lieutenant Governor': 'governor',
    'United States Senator': 'senate',
    'United States Representative': 'house__{district}',
    'Secretary of State': 'secretary_of_state',
    'State Auditor': 'state_auditor',
    'State Treasurer': 'state_treasurer',
    'Attorney General': 'attorney_general',
    'Commissioner of Public Lands': 'commissioner_of_public_lands',
    'State Representative': 'state_house__{district}',
}

for election_type in election_types:
    # request the statewide results page
    sw_url_pattern = (
        url_stub +
        'resultsSW.aspx?eid=2&type={election_type}&map=CTY'
    )
    sw_page_content = requests.get(sw_url_pattern.format(
        election_type=election_type
    )).content
    # parse out the table rows
    sw_page_soup = BeautifulSoup(sw_page_content, 'lxml')
    id_regex = re.compile(r'^MainContentxuwgResults_r_\d+$')
    trs = sw_page_soup.find_all('tr', id=id_regex)

    # iterate over table rows
    for tr in trs:
        # parse out the office and district from the race text
        race = tr.find('div', class_="divRace").text.split(' - District ')
        office = race[0].strip()
        try:
            district = race[1].strip()
        except IndexError:
            district = None
        # find the office slug (if it's defined)
        try:
            office_slug = office_slugs[office].format(district=district)
        except:
            print '   Unknown office: {0}'.format(office)
        else:
            # continue only if one of the defined offices
            print '   Getting precinct results for {0}...'.format(office)
            # parse out the county results page url
            cty_page_url = url_stub + tr.find(
                'span',
                class_='clickfont'
            ).find('a')['href']
            # request the county results page
            cty_page_content = requests.get(cty_page_url).content
            cty_page_soup = BeautifulSoup(cty_page_content, 'lxml')
            # parse out the "Export Precinct Level" button url
            export_url = url_stub + cty_page_soup.find(
                'a',
                id='MainContent_hlnkExportPrec'
            )['href']
            export_url = export_url.replace('/../', '/')

            with open(
                file_name_pattern.format(office=office_slug),
                'wb'
            ) as f:
                f.write(requests.get(export_url).content)

            sleep(2)

    sleep(2)
