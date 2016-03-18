import unicodecsv
import requests
from BeautifulSoup import BeautifulSoup

counties = ['Bernalillo', 'Catron', 'Chaves', 'Cibola', 'Colfax', 'Curry', 'De Baca', 'Dona Ana', 'Eddy', 'Grant', 'Guadalupe',
'Harding', 'Hidalgo', 'Lea', 'Lincoln', 'Los Alamos', 'Luna', 'McKinley', 'Mora', 'Otero', 'Quay', 'Rio Arriba', 'Roosevelt',
'San Juan', 'San Miguel', 'Sandoval', 'Santa Fe', 'Sierra', 'Socorro', 'Taos', 'Torrance', 'Union', 'Valencia']

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
			url = 'http://www.sos.state.nm.us/uploads/FileLinks/'+url_id+'/conty0'+getCounty(i+1)+'.HTM'+url_end+'.html'
			r = requests.get(url)
			soup = BeautifulSoup(r.text)
			tables = soup.findAll('table')
			tables = tables[:len(tables) - 2]
			hed = str(soup.find('h2'))

			for table in tables:
				office_district = table.findAll('center')[-1].getText().split('-')
				office = office_district[0].strip()
				district = ""

				if len(office_district) > 1:
					if office_district[1].split(' ')[1] == 'DISTRICT':
						district = office_district[1].split(' ')[-1];

				for row in table.findAll('tr'):
					col = row.findAll('td')
					county = counties[i+1]
					party = clean(col[1]).strip()
					candidate = clean(col[0]).strip()
					votes = clean(col[2]).strip()

					if candidate: 
						w.writerow([county, office, district, party, candidate, votes])
				

general_2000_output = '2000/20001107__nm__general__county.csv'
primary_2000_output = '2000/20000606__nm__primary__county.csv'
scrape(general_2000_output, '0900d3d66e844a4084e2f448b5dc0a6a', '')
scrape(primary_2000_output, '0900d3d66e844a4084e2f448b5dc0a6a', '_001')