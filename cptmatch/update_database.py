
from figment import models
from gi.repository import Appstream
from django.db import transaction

from distro.debian import *
from distro.fedora import *
from distro.tanglu import *

@transaction.commit_manually
def process_distro(distro):
    print("Collecting component information")
    dpool = Appstream.DataPool.new()

    dpool.set_appinstall_paths(None)
    dpool.set_xml_paths(distro.get_metadata_paths_xml())
    dpool.set_dep11_paths(distro.get_metadata_paths_dep11())

    dpool.initialize()
    dpool.update()

    cpts = dpool.get_components()

    print("Processing data for %s" % (distro.get_name()))
    with transaction.commit_on_success():
        for cpt in cpts:
            identifier = cpt.get_id().decode("utf-8")
            dbcpt = models.Component.objects.filter(identifier=identifier).first()
            if not dbcpt:
                dbcpt = models.Component()
            dbcpt.kind = Appstream.ComponentKind.to_string(cpt.get_kind()).decode("utf-8")
            dbcpt.identifier = identifier
            dbcpt.name = cpt.get_name().decode("utf-8")
            dbcpt.summary = cpt.get_summary().decode("utf-8")

            cptdesc = cpt.get_description().decode("utf-8").replace('\n', "<br/>")
            dbcpt.description = cptdesc

            dbcpt.license = cpt.get_project_license().decode("utf-8")
            homepage = cpt.get_url(Appstream.UrlKind.HOMEPAGE)
            if homepage:
                homepage = homepage.decode("utf-8")
            else:
                homepage = "#"
            dbcpt.homepage = homepage

            dbcpt.icon_url = cpt.get_icon_url().decode("utf-8")
            dbcpt.save()

            pkgname = cpt.get_pkgname()
            if pkgname:
                pkgname = pkgname.decode("utf-8")

            pkgs = distro.get_packages_info(pkgname)
            for pkg in pkgs:
                dbdistro = models.Distribution.objects.filter(codename=pkg.codename, name=distro.get_name()).first()
                if not dbdistro:
                   continue
                ver = models.ComponentVersion.objects.filter(component=dbcpt, version=pkg.version_upstream).first()
                if not ver:
                    ver = models.ComponentVersion()
                ver.component = dbcpt
                ver.version = pkg.version_upstream
                ver.save()
                dpk = models.DistroPackage()
                dpk.cpt_version = ver
                dpk.distro = dbdistro
                dpk.package_url = pkg.url
                dpk.save()


                for item_id in cpt.get_provided_items():
                    pitem = models.ProvidesItem()
                    pitem.cpt_version = ver
                    kind = Appstream.provides_item_get_kind(item_id)
                    pitem.kind = Appstream.provides_kind_to_string(kind).decode("utf-8")
                    value = Appstream.provides_item_get_value(item_id)
                    if not value:
                        continue
                    pitem.value = value.decode("utf-8")
                    pitem.save()

def import_data():
    distros = list()
    distros.append(DebianPkgInfoRetriever())
    distros.append(FedoraPkgInfoRetriever())
    distros.append(TangluPkgInfoRetriever())

    for distro in distros:
        for release in distro.get_releases():
            d = models.Distribution()
            d.name = distro.get_name()
            d.codename = release['codename']
            d.version = release['version']
            d.save()
        distro.update_caches()
        process_distro(distro)

