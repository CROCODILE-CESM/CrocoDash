from CrocoDash.shareable.identify import *

def test_diff_CESM_cases(skip_if_not_glade):
    print(diff_CESM_cases("/glade/u/home/manishrv/croc_cases/smoke.sink.cesm.1", "/glade/u/home/manishrv/croc_cases/smoke.sink.bgc.cesm.1"))

if __name__ == "__main__":
    test_diff_CESM_cases("Ntohginwsodf")
