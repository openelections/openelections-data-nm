import re
import requests
from bs4 import BeautifulSoup
from time import sleep

url_stub = 'http://electionresults.sos.state.nm.us/'
file_name_pattern = '20181106__nm__general__{office}.xlsx'
election_types = ['LGX']

office_slugs = {
    'Governor and Lieutenant Governor': 'governor',
    'United States Senator': 'senate',
    'United States Representative - DISTRICT 1': 'house__1',
    'United States Representative - DISTRICT 2': 'house__2',
    'United States Representative - DISTRICT 3': 'house__3',
    'Secretary of State': 'secretary_of_state',
    'State Auditor': 'state_auditor',
    'State Treasurer': 'state_treasurer',
    'Attorney General': 'attorney_general',
    'Commissioner of Public Lands': 'commissioner_of_public_lands',
    'State Representative': 'state_house__{district}',
    'State Representative - DISTRICT 1': 'state_house_1',
    'State Representative - DISTRICT 2': 'state_house_2',
    'State Representative - DISTRICT 3': 'state_house_3',
    'State Representative - DISTRICT 4': 'state_house_4',
    'State Representative - DISTRICT 5': 'state_house_5',
    'State Representative - DISTRICT 6': 'state_house_6',
    'State Representative - DISTRICT 7': 'state_house_7',
    'State Representative - DISTRICT 8': 'state_house_8',
    'State Representative - DISTRICT 9': 'state_house_9',
    'State Representative - DISTRICT 10': 'state_house_10',
    'State Representative - DISTRICT 11': 'state_house_11',
    'State Representative - DISTRICT 12': 'state_house_12',
    'State Representative - DISTRICT 13': 'state_house_13',
    'State Representative - DISTRICT 14': 'state_house_14',
    'State Representative - DISTRICT 15': 'state_house_15',
    'State Representative - DISTRICT 16': 'state_house_16',
    'State Representative - DISTRICT 17': 'state_house_17',
    'State Representative - DISTRICT 18': 'state_house_18',
    'State Representative - DISTRICT 19': 'state_house_19',
    'State Representative - DISTRICT 20': 'state_house_20',
    'State Representative - DISTRICT 21': 'state_house_21',
    'State Representative - DISTRICT 22': 'state_house_22',
    'State Representative - DISTRICT 23': 'state_house_23',
    'State Representative - DISTRICT 24': 'state_house_24',
    'State Representative - DISTRICT 25': 'state_house_25',
    'State Representative - DISTRICT 26': 'state_house_26',
    'State Representative - DISTRICT 27': 'state_house_27',
    'State Representative - DISTRICT 28': 'state_house_28',
    'State Representative - DISTRICT 29': 'state_house_29',
    'State Representative - DISTRICT 30': 'state_house_30',
    'State Representative - DISTRICT 31': 'state_house_31',
    'State Representative - DISTRICT 32': 'state_house_32',
    'State Representative - DISTRICT 33': 'state_house_33',
    'State Representative - DISTRICT 34': 'state_house_34',
    'State Representative - DISTRICT 35': 'state_house_35',
    'State Representative - DISTRICT 36': 'state_house_36',
    'State Representative - DISTRICT 37': 'state_house_37',
    'State Representative - DISTRICT 38': 'state_house_38',
    'State Representative - DISTRICT 39': 'state_house_39',
    'State Representative - DISTRICT 40': 'state_house_40',
    'State Representative - DISTRICT 41': 'state_house_41',
    'State Representative - DISTRICT 42': 'state_house_42',
    'State Representative - DISTRICT 43': 'state_house_43',
    'State Representative - DISTRICT 44': 'state_house_44',
    'State Representative - DISTRICT 45': 'state_house_45',
    'State Representative - DISTRICT 46': 'state_house_46',
    'State Representative - DISTRICT 47': 'state_house_47',
    'State Representative - DISTRICT 48': 'state_house_48',
    'State Representative - DISTRICT 49': 'state_house_49',
    'State Representative - DISTRICT 50': 'state_house_50',
    'State Representative - DISTRICT 51': 'state_house_51',
    'State Representative - DISTRICT 52': 'state_house_52',
    'State Representative - DISTRICT 53': 'state_house_53',
    'State Representative - DISTRICT 54': 'state_house_54',
    'State Representative - DISTRICT 55': 'state_house_55',
    'State Representative - DISTRICT 56': 'state_house_56',
    'State Representative - DISTRICT 57': 'state_house_57',
    'State Representative - DISTRICT 58': 'state_house_58',
    'State Representative - DISTRICT 59': 'state_house_59',
    'State Representative - DISTRICT 60': 'state_house_60',
    'State Representative - DISTRICT 61': 'state_house_61',
    'State Representative - DISTRICT 62': 'state_house_62',
    'State Representative - DISTRICT 63': 'state_house_63',
    'State Representative - DISTRICT 64': 'state_house_64',
    'State Representative - DISTRICT 65': 'state_house_65',
    'State Representative - DISTRICT 66': 'state_house_66',
    'State Representative - DISTRICT 67': 'state_house_67',
    'State Representative - DISTRICT 68': 'state_house_68',
    'State Representative - DISTRICT 69': 'state_house_69',
    'State Representative - DISTRICT 70': 'state_house_70'
}

for election_type in election_types:
    # request the statewide results page
    sw_url_pattern = (
        url_stub +
        'resultsSW.aspx?type={election_type}&map=CTY&lValue=100&gValue=001'
    )
    sw_page_content = requests.get(sw_url_pattern.format(
        election_type=election_type
    )).content
    # parse out the table rows
    sw_page_soup = BeautifulSoup(sw_page_content, 'lxml')
    idegex = re.compile(r'^MainContentxuwgResults_\d+$')
    trs = sw_page_soup.find('table', id='G_MainContentxuwgResults').find_all('tr')

    # iterate over table rows
    for tr in trs:
        if not tr.find('div', class_="divRace"):
            continue
        # parse out the office and district from the race text
        race = tr.find('div', class_="divRace").text.split(' - DISTRICT ')
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
        if office_slug:
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
