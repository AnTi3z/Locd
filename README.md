# Locd
Location tracker daemon (open route service wrapper)

See config.py for configuration

# Example usage:

## I. Command line

// Start daemon
> python locd.py start
***
// Get current tracker status
> python locd.py status
> > {"online": true, "req_cmd": "status", "status": {"cur_loc": [55.793913, 37.788678], "target_loc": [55.793913, 37.788678], "track": null, "speed": 0, "azimuth": null, "odo": 0}}
***
// Get current location (via working daemon)
> python locd.py cur
> > {"online": true, "req_cmd": "cur", "status": {"cur_loc": [55.793913, 37.788678]}}
***
// Move to some point
> python locd.py move 55.794 37.799
> > {"online": true, "req_cmd": "move", "status": {"cur_loc": [55.793912896183485, 37.788684644577785], "target_loc": [55.794, 37.799], "track": [[55.79391, 37.78887], [55.79383, 37.78888], [55.79383, 37.78898], [55.79343, 37.789], [55.79319, 37.78902], [55.79323, 37.79008], [55.79324, 37.79072], [55.79325, 37.79085], [55.79325, 37.79102], [55.79325, 37.79114], [55.79326, 37.79148], [55.79327, 37.79198], [55.7933, 37.7939], [55.7933, 37.79403], [55.7933, 37.79418], [55.7933, 37.79429], [55.79331, 37.79502], [55.79333, 37.7964], [55.79334, 37.79834], [55.79335, 37.79869], [55.79335, 37.79891], [55.79336, 37.79922], [55.79336, 37.79943], [55.79336, 37.79963], [55.79346, 37.79963], [55.79356, 37.79959], [55.79373, 37.79958], [55.79383, 37.79972], [55.79385, 37.79984], [55.79394, 37.79968], [55.79388, 37.79958], [55.79378, 37.79941], [55.79387, 37.79922], [55.79387, 37.79921], [55.7939, 37.79916], [55.79395, 37.79907], [55.79401, 37.79902], [55.794, 37.799]], "speed": 3, "azimuth": 91.58861428116876, "odo": 0.4169372717539469}}
***
// Stop daemon (current point will save)
> python locd.py stop
> > {"online": true, "req_cmd": "stop", "status": {}}
***
// Get current location from file (if daemon is not working)
> python locd.py cur
> > {"online": false, "req_cmd": "cur", "status": {"cur_loc": [55.79366059739212, 37.78898816113382]}}

## II. The same from script

>import locd
***
>locd.main(cmd='start')
>result = locd.main(cmd='status')
>result_json = json.dumps(locd.main(cmd='cur'))
>locd.main(cmd='move', lat=55.794, lon=37.799)

>locd.main(cmd='stop')

>locd.main(cmd='cur')
