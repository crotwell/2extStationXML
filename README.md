# 2extStationXML
code to help translate StationXML from IRIS DMC into ExtendedStationXML for ingestion into SIS

See the [wiki](https://github.com/crotwell/2extStationXML/wiki) for what little documentation exists.

**Warning:** IRIS is transitioning from the old svn and file based NRL to a new NRL web service. This change is substantial and the current code will not work with the new NRL. At this point, due to lack of time and demand, I do not expect to update this code to be compatible with the new NRL web service. SIS is also transitioning their bulk import system to function with URLs from
the new IRIS NRL, and as such extended StationXML generated by this
code may no longer be the best way to import legacy metadata if
you wish to preserve the connection from nominal responses to the NRL as the responses would be treated as custom responses even if they are nominal.
