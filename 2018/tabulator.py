import xlrd
import csv
import os
import re

# Python 3.4

def cell_finder(some_str, some_sheet):
    for row in range (some_sheet.nrows):
        for column in range(some_sheet.ncols):
            if some_str == some_sheet.cell(row, column).value:
                return (row, column)

header_row = ["county", "precinct", "office",
             "district", "party", "candidate", "votes"]

with open("20180605__nm__primary__precinct.csv", "a", encoding="utf-8") as csv_file:
    writer = csv.writer(csv_file)
    writer.writerow(header_row)

    all_files = os.listdir(".")

    # Don't grab the .py or .txt file in this directory

    files_to_tabulate = []
    for n in range(len(all_files)):
        if "xlsx" in all_files[n]:
            files_to_tabulate.append(all_files[n])

    # Loop through the filenames.
    # Grab the precinct and the office
    # from the filename

    for p in range(len(files_to_tabulate)):

        # These filenames are not the same pattern
        # some have - some have _
        # some have r some have Republican

        # So to extract the party, let's not modify the filename
        # Let's make a separate variable

        party = files_to_tabulate[p][23:]
        party = party.replace("d.xlsx", "Democratic.xlsx")
        party = party.replace("r.xlsx", "Republican.xlsx")
        party = party.replace("l.xlsx", "Libertarian.xlsx")
        party = party[-15:]
        party = party[:10]
        if party == 'ibertarian':
            party = 'Libertarian'

        district = files_to_tabulate[p][8:]
        district = re.sub('[^0-9]','', district)

        office = files_to_tabulate[p][23:]
        office = office.replace("_d", "__d")
        office = office.replace("_r", "__r")
        office = office.replace("_l", "__l")
        office = office.split("__")[0]
        office = office.replace("_", " ").title()

        # then open the file

        book = xlrd.open_workbook(files_to_tabulate[p])

        # grab only the sheets with a county name.
        # dont get the grand total sheets or the
        # breakdown by absentee or whatever.

        sheet_names = book.sheet_names()
        county_names = []

        for i in range(len(sheet_names)):
            if "County Results" in sheet_names[i]:
                pass
            else:
                county_names.append(sheet_names[i])

        # With that list of county names, aka sheets,
        # loop through each one and grab the votes

        for m in range(len(county_names)):
            sh = book.sheet_by_name(county_names[m])

            # get clean county name
            county_raw = sh.name
            county_split = county_raw.split("-")

            # look for the row where the data starts
            # it starts just after the row that contains
            # Precinct, name_1, name_2, etc
            #
            # Just in case it's not Excel row 7 in each one

            subhed_location = cell_finder("Precinct", sh)

            # The candidate names are everybody on this row
            # after from index 1 forward

            candidates = sh.row(subhed_location[0])[1:]

            # Look for the row where the data ends
            # I'd rather look for "TOTALS" and get an error
            # than do sh.nrows-1, just in case not all
            # sheets have a TOTAL row

            totals_location = cell_finder("TOTALS", sh)
            totals_row = totals_location[0]



            for j in range(len(candidates)):
                # start grabbing data on the row right after subhed_location
                counter = (subhed_location[0] + 1)

                while (counter < totals_row):

                    # append county name
                    # replace accented characters with unaccented

                    # new_row = [unicodedata.normalize('NFKD', county_split[0][:-1]).encode("latin-1", "ignore")]

                    new_row = [county_split[0][:-1]]

                    # Get the precinct number (ie, the cell at row[counter], column A)
                    # They're formated differently. Some say PCT, PRECINCT or just an int
                    # But there are some that have a letter in them, like PCT 012B
                    # And some are a long string like Precinct 1 - Lordsburg/West

                    precinct = sh.cell(counter, 0).value

                    if " " in precinct:
                        precinct = precinct.split(" ")[1]

                    if precinct[0] == str(0):
                        precinct = precinct[1:]

                    # some have two leading zeroes

                    if precinct[0] == str(0):
                        precinct = precinct[1:]

                    new_row.append(precinct)

                    #get the office name
                    new_row.append(office)

                    #the district will be blank in statewide office
                    new_row.append(district)

                    #party placeholder
                    new_row.append(party)

                    #candidate_name
                    #replace accented characters with unaccented ones
                    cand_name = candidates[j].value
                    # name_no_accent = unicodedata.normalize('NFKD', cand_name).encode("latin-1", "ignore")
                    new_row.append(cand_name)

                    # get the candidate votes (ie, the cell at counter, column j+1)
                    votes = int(sh.cell(counter, j+1).value)

                    new_row.append(votes)

                    print (new_row)
                    writer.writerow(new_row)
                    counter = counter + 1
