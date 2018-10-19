import re
import requests
from bs4 import BeautifulSoup
from time import sleep

url_stub = 'http://electionresults.sos.state.nm.us/'
file_name_pattern = '20180605__nm__primary__{office}.xlsx'
#the LGX designation may be different in the general depending on year
election_types = [ 'LGX'] #'FED', 'SW',

office_slugs = {
    'Governor - Democratic': 'governor_d',
    'Governor - Republican': 'governor_r',
    'Governor - Libertarian': 'governor_l',
    'Lieutenant Governor - Democratic': 'lt_governor_d',
    'Lieutenant Governor - Republican': 'lt_governor_r',
    'Lieutenant Governor - Libertarian': 'lt_governor_l',
    'United States Senator - Democratic': 'senate_d',
    'United States Senator - Republican': 'senate_r',
    'United States Senator - Libertarian': 'senate_l',
    'United States Representative - DISTRICT 1 - Democratic': 'house_1_d',
    'United States Representative - DISTRICT 1 - Republican': 'house_1_r',
    'United States Representative - DISTRICT 1 - Libertarian': 'house_1_l',
    'United States Representative - DISTRICT 2 - Democratic': 'house_2_d',
    'United States Representative - DISTRICT 2 - Republican': 'house_2_r',
    'United States Representative - DISTRICT 3 - Democratic': 'house_3_d',
    'United States Representative - DISTRICT 3 - Republican': 'house_3_d',
    'United States Representative - DISTRICT 3 - Libertarian': 'house_3_l',
    'Secretary of State - Democratic': 'secretary_of_state_d',
    'Secretary of State - Republican': 'secretary_of_state_r',
    'Secretary of State - Libertarian': 'secretary_of_state_l',
    'State Auditor - Democratic': 'state_auditor_d',
    'State Auditor - Republican': 'state_auditor_r',
    'State Treasurer - Democratic': 'state_treasurer_d',
    'State Treasurer - Republican': 'state_treasurer_r',
    'Attorney General - Democratic': 'attorney_general_d',
    'Attorney General - Republican': 'attorney_general_r',
    'Attorney General - Libertarian': 'attorney_general_l',
    'Commissioner of Public Lands - Democratic': 'commissioner_of_public_lands_d',
    'Commissioner of Public Lands - Republican': 'commissioner_of_public_lands_r',
    'Commissioner of Public Lands - Libertarian': 'commissioner_of_public_lands_l',
    'State Representative - DISTRICT 1 - Republican': 'state_house_1_r',
    'State Representative - DISTRICT 2 - Republican': 'state_house_2_r',
    'State Representative - DISTRICT 3 - Democratic': 'state_house_3_d',
    'State Representative - DISTRICT 3 - Republican': 'state_house_3_r',
    'State Representative - DISTRICT 4 - Democratic': 'state_house_4_d',
    'State Representative - DISTRICT 4 - Republican': 'state_house_4_r',
    'State Representative - DISTRICT 5 - Democratic': 'state_house_5_d',
    'State Representative - DISTRICT 6 - Democratic': 'state_house_6_d',
    'State Representative - DISTRICT 7 - Democratic': 'state_house_7_d',
    'State Representative - DISTRICT 7 - Republican': 'state_house_7_r',
    'State Representative - DISTRICT 8 - Democratic': 'state_house_8_d',
    'State Representative - DISTRICT 8 - Republican': 'state_house_8_r',
    'State Representative - DISTRICT 9 - Democratic': 'state_house_9_d',
    'State Representative - DISTRICT 10 - Democratic': 'state_house_10_d',
    'State Representative - DISTRICT 11 - Democratic': 'state_house_11_d',
    'State Representative - DISTRICT 12 - Democratic': 'state_house_12_d',
    'State Representative - DISTRICT 13 - Democratic': 'state_house_13_d',
    'State Representative - DISTRICT 14 - Democratic': 'state_house_14_d',
    'State Representative - DISTRICT 15 - Democratic': 'state_house_15_d',
    'State Representative - DISTRICT 15 - Republican': 'state_house_15_r',
    'State Representative - DISTRICT 16 - Democratic': 'state_house_16_d',
    'State Representative - DISTRICT 17 - Democratic': 'state_house_17_d',
    'State Representative - DISTRICT 17 - Republican': 'state_house_17_r',
    'State Representative - DISTRICT 18 - Democratic': 'state_house_18_d',
    'State Representative - DISTRICT 19 - Democratic': 'state_house_19_d',
    'State Representative - DISTRICT 20 - Democratic': 'state_house_20_d',
    'State Representative - DISTRICT 20 - Republican': 'state_house_20_r',
    'State Representative - DISTRICT 21 - Democratic': 'state_house_21_d',
    'State Representative - DISTRICT 22 - Democratic': 'state_house_22_d',
    'State Representative - DISTRICT 22 - Republican': 'state_house_22_r',
    'State Representative - DISTRICT 23 - Democratic': 'state_house_23_d',
    'State Representative - DISTRICT 23 - Republican': 'state_house_23_r',
    'State Representative - DISTRICT 24 - Democratic': 'state_house_24_d',
    'State Representative - DISTRICT 24 - Republican': 'state_house_24_r',
    'State Representative - DISTRICT 25 - Democratic': 'state_house_25_d',
    'State Representative - DISTRICT 25 - Republican': 'state_house_25_r',
    'State Representative - DISTRICT 26 - Democratic': 'state_house_26_d',
    'State Representative - DISTRICT 27 - Democratic': 'state_house_27_d',
    'State Representative - DISTRICT 27 - Republican': 'state_house_27_r',
    'State Representative - DISTRICT 28 - Democratic': 'state_house_28_d',
    'State Representative - DISTRICT 28 - Republican': 'state_house_28_r',
    'State Representative - DISTRICT 29 - Democratic': 'state_house_29_d',
    'State Representative - DISTRICT 29 - Republican': 'state_house_29_r',
    'State Representative - DISTRICT 30 - Democratic': 'state_house_30_d',
    'State Representative - DISTRICT 30 - Republican': 'state_house_30_r',
    'State Representative - DISTRICT 31 - Republican': 'state_house_31_r',
    'State Representative - DISTRICT 31 - Libertarian': 'state_house_31_l',
    'State Representative - DISTRICT 32 - Democratic': 'state_house_32_d',
    'State Representative - DISTRICT 32 - Republican': 'state_house_32_r',
    'State Representative - DISTRICT 33 - Democratic': 'state_house_33_d',
    'State Representative - DISTRICT 33 - Republican': 'state_house_33_r',
    'State Representative - DISTRICT 34 - Democratic': 'state_house_34_d',
    'State Representative - DISTRICT 35 - Democratic': 'state_house_35_d',
    'State Representative - DISTRICT 35 - Republican': 'state_house_35_r',
    'State Representative - DISTRICT 36 - Democratic': 'state_house_36_d',
    'State Representative - DISTRICT 36 - Republican': 'state_house_36_r',
    'State Representative - DISTRICT 37 - Democratic': 'state_house_37_d',
    'State Representative - DISTRICT 37 - Republican': 'state_house_37_r',
    'State Representative - DISTRICT 38 - Democratic': 'state_house_38_d',
    'State Representative - DISTRICT 38 - Republican': 'state_house_38_r',
    'State Representative - DISTRICT 39 - Democratic': 'state_house_39_d',
    'State Representative - DISTRICT 39 - Republican': 'state_house_39_r',
    'State Representative - DISTRICT 40 - Democratic': 'state_house_40_d',
    'State Representative - DISTRICT 41 - Democratic': 'state_house_41_d',
    'State Representative - DISTRICT 42 - Democratic': 'state_house_42_d',
    'State Representative - DISTRICT 43 - Democratic': 'state_house_43_d',
    'State Representative - DISTRICT 43 - Republican': 'state_house_43_r',
    'State Representative - DISTRICT 44 - Democratic': 'state_house_44_d',
    'State Representative - DISTRICT 44 - Republican': 'state_house_44_r',
    'State Representative - DISTRICT 45 - Democratic': 'state_house_45_d',
    'State Representative - DISTRICT 46 - Democratic': 'state_house_46_d',
    'State Representative - DISTRICT 47 - Democratic': 'state_house_47_d',
    'State Representative - DISTRICT 48 - Democratic': 'state_house_48_d',
    'State Representative - DISTRICT 49 - Democratic': 'state_house_49_d',
    'State Representative - DISTRICT 49 - Republican': 'state_house_49_r',
    'State Representative - DISTRICT 50 - Democratic': 'state_house_50_d',
    'State Representative - DISTRICT 51 - Democratic': 'state_house_51_d',
    'State Representative - DISTRICT 51 - Republican': 'state_house_51_r',
    'State Representative - DISTRICT 52 - Democratic': 'state_house_52_d',
    'State Representative - DISTRICT 52 - Republican': 'state_house_52_r',
    'State Representative - DISTRICT 53 - Democratic': 'state_house_53_d',
    'State Representative - DISTRICT 53 - Republican': 'state_house_53_r',
    'State Representative - DISTRICT 54 - Republican': 'state_house_54_r',
    'State Representative - DISTRICT 55 - Republican': 'state_house_55_r',
    'State Representative - DISTRICT 56 - Republican': 'state_house_56_r',
    'State Representative - DISTRICT 57 - Democratic': 'state_house_57_d',
    'State Representative - DISTRICT 57 - Republican': 'state_house_57_r',
    'State Representative - DISTRICT 58 - Republican': 'state_house_58_r',
    'State Representative - DISTRICT 59 - Republican': 'state_house_59_r',
    'State Representative - DISTRICT 59 - Libertarian': 'state_house_59_l',
    'State Representative - DISTRICT 60 - Democratic': 'state_house_60_d',
    'State Representative - DISTRICT 60 - Republican': 'state_house_60_r',
    'State Representative - DISTRICT 61 - Republican': 'state_house_61_r',
    'State Representative - DISTRICT 62 - Republican': 'state_house_62_r',
    'State Representative - DISTRICT 63 - Democratic': 'state_house_63_d',
    'State Representative - DISTRICT 63 - Republican': 'state_house_63_r',
    'State Representative - DISTRICT 64 - Republican': 'state_house_64_r',
    'State Representative - DISTRICT 65 - Democratic': 'state_house_65_d',
    'State Representative - DISTRICT 66 - Republican': 'state_house_66_r',
    'State Representative - DISTRICT 67 - Democratic': 'state_house_67_d',
    'State Representative - DISTRICT 67 - Republican': 'state_house_67_r',
    'State Representative - DISTRICT 68 - Democratic': 'state_house_68_d',
    'State Representative - DISTRICT 68 - Republican': 'state_house_68_r',
    'State Representative - DISTRICT 69 - Democratic': 'state_house_69_d',
    'State Representative - DISTRICT 70 - Democratic': 'state_house_70_d'
}

for election_type in election_types:
    # request the statewide results page
    sw_url_pattern = (
        url_stub +
        'resultsSW.aspx?eid=112&type={election_type}&map=CTY&lValue=100&gValue=001'
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
