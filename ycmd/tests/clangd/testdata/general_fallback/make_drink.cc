#include "make_drink.h"

using namespace Test;

struct Testing {
  int a_really_really_really_really_annoyingly_long_method_name(
    int with,
    char a,
    bool lot,
    const char * of,
    Testing& arguments
  );
  int a_really_really_really_really_annoyingly_long_method_name(
    int with_only_one_really_really_really_annoyingly_long_argument
  );
};

int main( int , char ** )
{
  make_drink( TypeOfDrink::COFFEE, 10.0, Flavour::ELDERFLOWER );
  make_drink( TypeOfDrink::JUICE, Temperature::COLD, 1 );

  Testing t;
  t.a_really_really_really_really_annoyingly_long_method_name( 
}
