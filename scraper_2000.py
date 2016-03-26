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
			hed = str(soup.find('h2'))
			tables = soup.findAll('table')

			if type == 'general':
				tables = tables[:len(tables) - 2]

			count = 0
			for table in tables:
				count = count + 1
				
				office_district = ''
				district = ''

				if count > 1:
					office_district = table.findAll('h2')[0].getText().split('-')
				else:
					office_district = ['PRESIDENT OF THE UNITED STATES']
				
				if len(office_district) > 1:
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
					office = office_district[0]
					party = clean(col[1]).strip()
					candidate = clean(col[0]).strip()
					votes = clean(col[2]).strip()

					if candidate: 
						w.writerow([county, office, district, party, candidate, votes])
				

general_2000_output = '2000/20001107__nm__general__county.csv'
scrape(general_2000_output, '0900d3d66e844a4084e2f448b5dc0a6a', '', 'general')

primary_2000_output = '2000/20000606__nm__primary__county.csv'
scrape(primary_2000_output, '0900d3d66e844a4084e2f448b5dc0a6a', '_001', 'primary')