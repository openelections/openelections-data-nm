import unicodecsv
import requests
from BeautifulSoup import BeautifulSoup

counties = ['Santa Fe', 'Bernalillo', 'Eddy', 'Chaves', 'Curry', 'Lea', 'Dona Ana', 'Grant', 'Colfax', 'Quay', 'Roosevelt', 'San Miguel', 
'McKinley', 'Valencia', 'Otero', 'San Juan', 'Rio Arriba', 'Union', 'Luna', 'Taos', 'Sierra', 'Torrance', 'Hidalgo', 'Guadalupe', 'Socorro',
'Lincoln', 'De Baca', 'Catron', 'Sandoval', 'Mora', 'Harding', 'Los Alamos', 'Cibola']

district_exclusions = ['(Retention)', '##']

def getCounty(i):
	if i < 10:
		return '0' + str(i)
	else:
		return str(i)

def clean(text):
	return text.getText().replace('mstheme','').replace(',','').replace('&nbsp;','').replace('/', 'and')

def scrape(output_file, url_id, url_end, type):
	with open(output_file, 'wb') as csvfile:
		w = unicodecsv.writer(csvfile, encoding='utf-8')
		headers = ['county', 'office', 'district', 'party', 'candidate', 'votes']
		w.writerow(headers)

		for i in range(len(counties)):
			
			url = ''
			if counties[i] == 'Santa Fe':
				url = 'http://www.sos.state.nm.us/uploads/FileLinks/'+url_id+'/conty000'+url_end+'.htm' 	
			else:
				url = 'http://www.sos.state.nm.us/uploads/FileLinks/'+url_id+'/conty0'+getCounty(i)+'.HTM'+url_end+'.html'

			r = requests.get(url)
			soup = BeautifulSoup(r.text)
			hed = soup.findAll('h2')
			tables = soup.findAll('table')

			if type == 'primary':
				tables = tables
			else:
				tables = tables[:len(tables) - 2]


			count = ''
			if type == 'primary':
				count = 0
			else:
				count = 2

			for table in tables:
				count = count + 1

				office_district = ''
				district = ''
				
				if type == 'primary':
					office_district = hed[count].getText().split('-')
				else:
					if count > 2:
						office_district = hed[count].getText().split('-')
							
				if len(office_district) > 1:
					if office_district[1].split(' ')[1] == 'DISTRICT' or office_district[1].split(' ')[1] == 'DIVISION':
						district = office_district[1].split(' ')[-1];
						if district not in district_exclusions:
							district = int(district)
						else:
							district = ''

				for row in table.findAll('tr'):
					col = row.findAll('td')
					county = counties[i]
					office = office_district[0].replace('mstheme', 'UNITED STATES SENATOR')
					party = clean(col[1]).strip()
					candidate = clean(col[0]).strip()
					votes = clean(col[2]).strip()

					if candidate:
						w.writerow([county, office, district, party, candidate, votes])
				

general_2002_output = '2002/20021105__nm__general__county.csv'
scrape(general_2002_output, '308947684091406b930f2fc3974c9057', '', 'general')

primary_2002_output = '2002/20020604__nm__primary__county.csv'
scrape(primary_2002_output, '308947684091406b930f2fc3974c9057', '_001', 'primary')