package implementations

// Some interface
type Wigdet interface {
  WibbleWobble( test int, testing string ) ( string, bool )
}

// This struct does _not_ implement the Widget interface, but does use it
type Wibble struct {
  value string
  happy bool
}

func (self *Wibble) Wobble( widget Wigdet ) {
  foo, bar := widget.WibbleWobble( 1, self.value )

  self.happy = bar
  self.value = foo
}

// This struxt implements the Widget interface
type Wobble struct {}

func (self Wobble) WibbleWobble( test int, testing string ) ( string, bool ) {
  return "Hello", true
}

// Use the bits above
func main() {
  wibble := Wibble{ value: "test", happy: true }
  wobble := Wobble{}

  wibble.Wobble( wobble )
}
