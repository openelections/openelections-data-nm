import unicodecsv

headers = ['county', 'office', 'district', 'party', 'candidate', 'votes']
counties = ['Bernalillo', 'Catron', 'Chaves', 'Cibola', 'Colfax', 'Curry', 'De Baca', 'Dona Ana', 'Eddy', 'Grant', 'Guadalupe',
'Harding', 'Hidalgo', 'Lea', 'Lincoln', 'Los Alamos', 'Luna', 'McKinley', 'Mora', 'Otero', 'Quay', 'Rio Arriba', 'Roosevelt',
'San Juan', 'San Miguel', 'Sandoval', 'Santa Fe', 'Sierra', 'Socorro', 'Taos', 'Torrance', 'Union', 'Valencia']

statewide = ['PRESIDENT AND VICE PRESIDENT OF THE UNITED STATES', 'UNITED STATES SENATOR', 'JUSTICE OF THE SUPREME COURT',
'JUDGE OF THE COURT OF APPEALS', 'GOVERNOR and LIEUTENANT GOVERNOR', 'SECRETARY OF STATE', 'STATE TREASURER', 'ATTORNEY GENERAL',
'COMMISSIONER OF PUBLIC LANDS', 'STATE AUDITOR', 'PRESIDENT OF THE UNITED STATES']
legislative = ['UNITED STATES REPRESENTATIVE', 'STATE SENATOR', 'STATE REPRESENTATIVE']
offices = statewide + legislative

with open('2008/20080603__nm__primary.csv', 'wb') as csvfile:
    w = unicodecsv.writer(csvfile, encoding='utf-8')
    w.writerow(headers)

    lines = open('/Users/DW-Admin/code/openelections-data-nm/2008primary.txt').readlines()
    for line in lines:
        parsed_line = line.split('\t')
#        print parsed_line
#        if 'CANDIDATE' in line:
#            continue
        if parsed_line[0].strip() in offices:
            office = parsed_line[0].strip()
        elif 'DISTRICT' in parsed_line[0] and office:
            district = parsed_line[0].strip().split('DISTRICT ')[1]
        elif len([p for p in parsed_line if p != '']) == 1:
            continue
        elif 'Canvass of Returns' in line:
            party = parsed_line[0].strip()
        elif len(parsed_line[1:]) > 2:
            candidate = parsed_line[0]
            vote_totals = [int(p.strip()) for p in parsed_line[1:]]
            total = vote_totals[33]
            county_totals = vote_totals[0:33]
            combo = zip(counties, county_totals)
            if office not in offices:
                continue
            if office in statewide:
                district = None
            for county, votes in combo:
                if office not in statewide and votes == 0:
                    continue
                else:
                    w.writerow([county, office, district, party, candidate, votes])
            w.writerow([None, office, district, party, candidate, total])
