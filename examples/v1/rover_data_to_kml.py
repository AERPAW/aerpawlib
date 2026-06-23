import csv
import os
import xml.dom.minidom
from argparse import ArgumentParser


def createStringPath(kmlDoc, rows):
    """Create a string path consisting of every coordinate in the csv"""
    placemarkElement = kmlDoc.createElement("Placemark")

    # Name the string path
    nameElement = kmlDoc.createElement("name")
    placemarkElement.appendChild(nameElement)
    nameElement.appendChild(kmlDoc.createTextNode("search flight path"))

    # Create a linestring consisting of an array of coordinates
    lineElement = kmlDoc.createElement("LineString")
    placemarkElement.appendChild(lineElement)

    # Set display attributes of line to extrude to the ground
    extrudeElement = kmlDoc.createElement("extrude")
    extrudeElement.appendChild(kmlDoc.createTextNode("1"))
    altitudeModeElement = kmlDoc.createElement("altitudeMode")
    altitudeModeElement.appendChild(kmlDoc.createTextNode("relativeToGround"))
    coordinatesElement = kmlDoc.createElement("coordinates")

    # Construct array of coordinate strings
    coordinates_str = ""
    for row in rows:
        # longitude, latitude, altitude
        coordinates_str += f"{row[0]},{row[1]},{row[2]} "

    coordinatesElement.appendChild(kmlDoc.createTextNode(coordinates_str))
    lineElement.appendChild(extrudeElement)
    lineElement.appendChild(altitudeModeElement)
    lineElement.appendChild(coordinatesElement)

    return placemarkElement


def createPlacemark(kmlDoc, row, row_number):
    """For a single entry in the CSV file create a point placemark labeled with
    the row number and the RSSI measurement"""
    placemarkElement = kmlDoc.createElement("Placemark")

    # Use row number of CSV to label this placemark
    nameElement = kmlDoc.createElement("name")
    nameElement.appendChild(kmlDoc.createTextNode(str(row_number)))
    placemarkElement.appendChild(nameElement)

    # Create data element to store measurement
    extElement = kmlDoc.createElement("ExtendedData")
    placemarkElement.appendChild(extElement)

    # Store row number and RSSI measurement as data of this placemark
    dataElement = kmlDoc.createElement("Data")
    dataElement.setAttribute("name", str(row_number))
    valueElement = kmlDoc.createElement("value")
    dataElement.appendChild(valueElement)
    # RSSI Measurement
    valueText = kmlDoc.createTextNode(str(row[3]))
    valueElement.appendChild(valueText)
    extElement.appendChild(dataElement)

    # Create coordinates point for the placemark
    pointElement = kmlDoc.createElement("Point")
    placemarkElement.appendChild(pointElement)

    # Make points have correct altitude
    altitudeModeElement = kmlDoc.createElement("altitudeMode")
    altitudeModeElement.appendChild(kmlDoc.createTextNode("relativeToGround"))
    pointElement.appendChild(altitudeModeElement)

    coorElement = kmlDoc.createElement("coordinates")
    pointElement.appendChild(coorElement)
    coordinates = f"{row[0]},{row[1]},{row[2]}"
    coorElement.appendChild(kmlDoc.createTextNode(coordinates))

    return placemarkElement


def createKML(rows, fileName):
    """Construct a KML file from the rows of a CSV containing a search path coordinates and
    RSSI values at each location"""

    # Setup the KML document
    kmlDoc = xml.dom.minidom.Document()

    kmlElement = kmlDoc.createElementNS("http://earth.google.com/kml/2.2", "kml")
    kmlElement.setAttribute("xmlns", "http://earth.google.com/kml/2.2")
    kmlElement = kmlDoc.appendChild(kmlElement)
    documentElement = kmlDoc.createElement("Document")
    documentElement = kmlElement.appendChild(documentElement)

    # iterate through each row in the csv and construct a place marker
    row_num = 1
    for row in rows:
        placemarkElement = createPlacemark(kmlDoc, row, row_num)
        documentElement.appendChild(placemarkElement)
        row_num += 1
    # create a path showing the complete rover search path
    placemarkElement = createStringPath(kmlDoc, rows)
    documentElement.appendChild(placemarkElement)

    # Save kml to file
    kmlFile = open(fileName, "wb")
    kmlFile.write(kmlDoc.toprettyxml("  ", newl="\n", encoding="utf-8"))


if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument(
        "--input",
        help="Input CSV file of search data",
        required=True,
    )
    # If not provided, the output file will be named identical to the input with a different extension
    parser.add_argument("--output", help="Output KML file of search data", required=False, default="")

    args = parser.parse_args()

    in_file = args.input
    out_file = args.output
    if out_file == "":
        # extract name of input file with no extension
        in_path = os.path.splitext(in_file)
        out_file = f"{in_path[0]}.kml"

    f = open(in_file)
    reader = csv.reader(f)
    # Skip the header line.
    next(reader)
    rows = list(reader)
    # throw out the header of the csv file
    createKML(rows, out_file)
