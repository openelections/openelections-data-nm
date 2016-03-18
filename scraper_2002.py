import unicodecsv
import requests
from BeautifulSoup import BeautifulSoup


counties = ['Santa Fe', 'Bernalillo', 'Eddy', 'Chaves', 'Curry', 'Lea', 'Dona Ana', 'Grant', 'Colfax', 'Quay', 'Roosevelt', 'San Miguel', 
'McKinley', 'Valencia', 'Otero', 'San Juan', 'Rio Arriba', 'Union', 'Luna', 'Taos', 'Sierra', 'Torrance', 'Hidalgo', 'Guadalupe', 'Socorro',
'Lincoln', 'De Baca', 'Catron', 'Sandoval', 'Mora', 'Harding', 'Los Alamos', 'Cibola']


def getCounty(i):
	if i < 10:
		return '0' + str(i)
	else:
		return str(i)

def clean(text):
	return text.getText().replace('mstheme','').replace(',','').replace('&nbsp;','').replace('/', 'and')

def scrape(output_file, url_id, url_end):
	with open(output_file, 'wb') as csvfile:
		w = unicodecsv.writer(csvfile, encoding='utf-8')
		headers = ['county', 'office', 'district', 'party', 'candidate', 'votes']
		w.writerow(headers)

		for i in range(len(counties)):
			
			url = ''
			if counties[i] == 'Santa Fe':
				url = 'http://www.sos.state.nm.us/uploads/FileLinks/308947684091406b930f2fc3974c9057/conty000.htm' 	
			else:
				url = 'http://www.sos.state.nm.us/uploads/FileLinks/'+url_id+'/conty0'+getCounty(i)+'.HTM'+url_end+'.html'

			
			
			r = requests.get(url)
			soup = BeautifulSoup(r.text)
			tables = soup.findAll('table')
			tables = tables[:len(tables) - 2]
			hed = soup.findAll('h2')


			
			count = 0
			for table in tables:
				count = count + 1

				office_district = hed[count].getText().split('-')
			
				if count > 3:
					office = office_district[0].strip()
				else:
					office = 'UNITED STATES SENATOR'
				district = ""

				if len(office_district) > 1:
					if office_district[1].split(' ')[1] == 'DISTRICT':
						district = office_district[1].split(' ')[-1];

				for row in table.findAll('tr'):
					col = row.findAll('td')
					county = counties[i]
					party = clean(col[1]).strip()
					candidate = clean(col[0]).strip()
					votes = clean(col[2]).strip()

					

					if candidate: 
						w.writerow([county, office, district, party, candidate, votes])
				

general_2002_output = '2002/20021105__nm__general__county.csv'
# primary_2002_output = '2002/20020604__nm__primary__county.csv'
scrape(general_2002_output, '308947684091406b930f2fc3974c9057', '')
# scrape(primary_2002_output, '308947684091406b930f2fc3974c9057', '_001')