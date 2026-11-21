"""Single business-image layout. Historical three-component publication library stays intact."""

from scripts import release as legacy

COMPONENTS=('app',)
VERSION=legacy.VERSION
SHA=legacy.SHA
validate_inputs=legacy.validate_inputs
digest=legacy.digest

def image(component):
    if component not in COMPONENTS:raise ValueError('Unknown unified-image component')
    return 'life-journal'

def names(component,version):
    image(component)
    if not(VERSION.fullmatch(version) or SHA.fullmatch(version)):raise ValueError('Invalid version')
    name=f'life-journal-{component}-{version}-amd64.tar'
    return name,name+'.sha256'


def verify_bundle(root,revision,version,commands):
    specifications={c:{'name':names(c,version)[0],'checksum':names(c,version)[1],'reference':image(c)+':'+version} for c in COMPONENTS}
    return legacy.verify_bundle(root,revision,version,commands,specifications=specifications)
