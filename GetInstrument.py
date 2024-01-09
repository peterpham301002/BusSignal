import pyvisa as visa

# Create a PyVISA resource manager
rm = visa.ResourceManager()

try:
    # List all available resources (instruments)
    resources = rm.list_resources()

    if len(resources) == 0:
        print("No instruments found.")
    else:
        print("Available instruments:")
        for idx, res in enumerate(resources):
            print(f"{idx + 1}: {res}")

        # Automatically select the first instrument found
        instrument_visa_address = resources[0]

        # Open a connection to the selected instrument
        oscilloscope = rm.open_resource(instrument_visa_address)

        # Query the identification string of the instrument
        identification = oscilloscope.query('*IDN?')
        print("\nConnected to:", identification)
        active_channels = oscilloscope.query('DATA:SOURCE?')
        print("Active Channels:", active_channels)
        # Perform operations, send commands, or query data as per your requirements
        # For example:
        # oscilloscope.write('SINGLE')  # Sends the command to trigger a single acquisition
        # data = oscilloscope.query_ascii_values('CURVE?')  # Queries waveform data

        # Close the connection when finished
        oscilloscope.close()

except visa.VisaIOError as e:
    print("An error occurred:", e)

finally:
    # Close the resource manager at the end
    rm.close()